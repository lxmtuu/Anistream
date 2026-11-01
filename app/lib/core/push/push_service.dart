import 'dart:async';
import 'dart:math';

import 'package:dio/dio.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../app/env.dart';

/// Đăng ký nhận thông báo "tập mới vừa ra" + mở đúng màn hình khi bấm.
///
/// Thiết kế:
///  • **Không cần đăng nhập**: mỗi thiết bị có `device_id` ngẫu nhiên lưu cục bộ;
///    backend lưu (device_id, token, anime_ids) trong bảng `push_subscriptions`.
///  • Danh sách bộ muốn nhận tin = **watchlist** của người dùng → gọi
///    [syncSubscriptions] mỗi khi watchlist thay đổi.
///  • Toàn bộ nằm trong try/catch: chưa cấu hình Firebase thì app **vẫn chạy bình thường**,
///    chỉ là không có thông báo.
///
/// Bật push:
///   1. `dart pub global activate flutterfire_cli && flutterfire configure`
///   2. `flutter run --dart-define=USE_MOCK=false --dart-define=API_BASE=… --dart-define=ANON_KEY=…`
class PushService {
  PushService._();
  static final PushService instance = PushService._();

  bool _ready = false;
  bool get ready => _ready;

  String? _token;
  String? _deviceId;

  FirebaseMessaging? _messaging;
  final Dio _dio = Dio(BaseOptions(
    connectTimeout: const Duration(seconds: 12),
    receiveTimeout: const Duration(seconds: 12),
  ));

  /// Gọi 1 lần trong `main()`. Không await để không chặn UI khởi động.
  Future<void> init({void Function(String route)? onRouteFromNotification}) async {
    if (kIsWeb) return; // web push cần VAPID riêng → v1.1

    try {
      await Firebase.initializeApp();
      _messaging = FirebaseMessaging.instance;

      final settings = await _messaging!.requestPermission(
        alert: true,
        badge: true,
        sound: true,
      );
      if (settings.authorizationStatus == AuthorizationStatus.denied) {
        debugPrint('PushService: người dùng từ chối quyền thông báo');
        return;
      }

      await _loadDeviceId();

      _token = await _messaging!.getToken();
      _messaging!.onTokenRefresh.listen((t) {
        _token = t;
        debugPrint('PushService: token refresh');
      });

      // bấm vào thông báo khi app đang chạy nền
      FirebaseMessaging.onMessageOpenedApp.listen(
        (m) => _handleRoute(m, onRouteFromNotification),
      );

      // bấm vào thông báo khi app bị kill
      final initial = await _messaging!.getInitialMessage();
      if (initial != null) _handleRoute(initial, onRouteFromNotification);

      _ready = true;
      debugPrint('PushService: sẵn sàng (device ${_deviceId?.substring(0, 8)}…)');
    } catch (e) {
      // Chưa `flutterfire configure` → bỏ qua, app vẫn chạy
      debugPrint('PushService: chưa bật được push ($e)');
    }
  }

  void _handleRoute(
    RemoteMessage m,
    void Function(String route)? onRoute,
  ) {
    final route = m.data['route'];
    if (route is String && route.startsWith('/')) {
      debugPrint('PushService: mở $route');
      onRoute?.call(route);
    }
  }

  Future<void> _loadDeviceId() async {
    final prefs = await SharedPreferences.getInstance();
    var id = prefs.getString('anistream_device_id');
    if (id == null || id.isEmpty) {
      id = _randomId();
      await prefs.setString('anistream_device_id', id);
    }
    _deviceId = id;
  }

  static String _randomId() {
    final r = Random.secure();
    final bytes = List<int>.generate(16, (_) => r.nextInt(256));
    return bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  }

  String get _platform {
    if (kIsWeb) return 'web';
    switch (defaultTargetPlatform) {
      case TargetPlatform.iOS:
        return 'ios';
      case TargetPlatform.android:
        return 'android';
      default:
        return 'desktop';
    }
  }

  /// Đồng bộ danh sách bộ muốn nhận thông báo (thường = watchlist).
  /// Gọi trong `ref.listen(watchlistProvider, …)`.
  Future<void> syncSubscriptions(Set<int> animeIds) async {
    if (!_ready || _token == null || _deviceId == null) return;
    if (Env.restBase.isEmpty || Env.anonKey.isEmpty) {
      debugPrint('PushService: thiếu API_BASE/ANON_KEY → bỏ qua sync');
      return;
    }

    try {
      await _dio.post(
        '${Env.restBase}/rest/v1/push_subscriptions'
        '?on_conflict=device_id,token',
        data: {
          'device_id': _deviceId,
          'token': _token,
          'platform': _platform,
          'anime_ids': animeIds.toList(),
          'is_active': true,
        },
        options: Options(
          headers: {
            'apikey': Env.anonKey,
            'Authorization': 'Bearer ${Env.anonKey}',
            'Content-Type': 'application/json',
            'Prefer': 'resolution=merge-duplicates,return=minimal',
          },
        ),
      );
      debugPrint('PushService: đã đồng bộ ${animeIds.length} bộ');
    } catch (e) {
      debugPrint('PushService: sync lỗi ($e)');
    }
  }

  /// Tắt thông báo cho thiết bị này (dùng ở màn Cài đặt).
  Future<void> disable() async {
    if (_token == null) return;
    try {
      await _dio.patch(
        '${Env.restBase}/rest/v1/push_subscriptions'
        '?device_id=eq.$_deviceId&token=eq.$_token',
        data: {'is_active': false},
        options: Options(
          headers: {
            'apikey': Env.anonKey,
            'Authorization': 'Bearer ${Env.anonKey}',
            'Prefer': 'return=minimal',
          },
        ),
      );
    } catch (e) {
      debugPrint('PushService: disable lỗi ($e)');
    }
  }
}
