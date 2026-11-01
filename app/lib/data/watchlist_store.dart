import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// Nơi lưu "Thư viện" (watchlist).
///
/// Tách thành interface để đổi backend lưu trữ mà **không sửa UI**:
///  • hôm nay  → [PrefsWatchlistStore] (SharedPreferences: bền qua lần mở app,
///    chạy được cả web/desktop, không cần codegen, không cần đăng nhập)
///  • bước sau → Drift (SQLite, offline + query) hoặc bảng `watchlist` trên
///    Supabase khi có đăng nhập (xem `DECISION.md` §5 mục 4, RLS đã sẵn trong
///    `db/schema.sql`).
///
/// Vì sao chưa dùng Drift ngay: Drift cần `build_runner` sinh code, nghĩa là
/// người mới clone repo phải chạy codegen trước khi `flutter run` được. Ở quy mô
/// v1 (vài chục bộ theo dõi) SharedPreferences thừa sức; đổi sang Drift chỉ là
/// thay một implementation của interface này.
abstract class WatchlistStore {
  Future<Set<int>> load();
  Future<void> save(Set<int> ids);
}

/// Lưu bằng SharedPreferences dưới dạng JSON `[1,2,3]`.
/// Mọi lỗi đọc (dữ liệu hỏng, kiểu cũ…) đều trả về rỗng — thà mất thư viện còn
/// hơn app crash lúc khởi động.
class PrefsWatchlistStore implements WatchlistStore {
  static const String key = 'anistream_watchlist_v1';

  @override
  Future<Set<int>> load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(key);
      if (raw == null || raw.isEmpty) return <int>{};

      final decoded = jsonDecode(raw);
      if (decoded is! List) return <int>{};

      final ids = <int>{};
      for (final e in decoded) {
        if (e is int) {
          ids.add(e);
        } else if (e is num) {
          ids.add(e.toInt());
        } else if (e is String) {
          final n = int.tryParse(e);
          if (n != null) ids.add(n);
        }
      }
      return ids;
    } catch (_) {
      return <int>{};
    }
  }

  @override
  Future<void> save(Set<int> ids) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(key, jsonEncode(ids.toList()..sort()));
    } catch (_) {
      // Bộ nhớ đầy / nền tảng không hỗ trợ: bỏ qua, watchlist vẫn dùng được
      // trong phiên hiện tại (chỉ là không bền qua lần mở sau).
    }
  }
}

/// Dùng cho test và cho môi trường không có storage (vd. preview tĩnh).
class MemoryWatchlistStore implements WatchlistStore {
  Set<int> _ids = <int>{};

  MemoryWatchlistStore([Set<int>? initial]) : _ids = {...?initial};

  @override
  Future<Set<int>> load() async => {..._ids};

  @override
  Future<void> save(Set<int> ids) async => _ids = {...ids};
}
