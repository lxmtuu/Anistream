import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../app/env.dart';
import '../core/models/anime.dart';
import '../core/models/home_feed.dart';
import 'mock_data.dart';
import 'watchlist_store.dart';

/// Hợp đồng dữ liệu — UI chỉ biết interface này, nên đổi backend không sửa UI.
abstract class AnimeRepository {
  Future<HomeFeed> loadHome();
  Future<List<Anime>> search(String query);

  /// Chi tiết 1 bộ theo slug — dùng khi mở deep link `/anime/<slug>` cho bộ
  /// không nằm trong feed trang chủ (vd. bấm thông báo "tập mới vừa ra").
  /// Trả `null` nếu không tồn tại.
  Future<Anime?> fetchAnime(String slug);
}

/// ── Mock: dữ liệu THẬT sinh từ AniList + YouTube (xem tools/gen_mock.py) ──
class MockAnimeRepository implements AnimeRepository {
  HomeFeed? _cache;

  Future<HomeFeed> _feed() async {
    if (_cache != null) return _cache!;
    // giả lập độ trễ mạng để skeleton loading được kiểm tra thật
    await Future<void>.delayed(const Duration(milliseconds: 450));
    _cache = HomeFeed.fromJson(
      jsonDecode(kMockDataJson) as Map<String, dynamic>,
    );
    return _cache!;
  }

  @override
  Future<HomeFeed> loadHome() => _feed();

  @override
  Future<List<Anime>> search(String query) async {
    final feed = await _feed();
    final q = _norm(query);
    if (q.isEmpty) return const [];
    return feed.anime.where((a) {
      return _norm(a.title).contains(q) ||
          _norm(a.titleVi ?? '').contains(q) ||
          _norm(a.titleNative ?? '').contains(q);
    }).toList();
  }

  @override
  Future<Anime?> fetchAnime(String slug) async {
    final feed = await _feed();
    return feed.bySlug(slug);
  }

  static String _norm(String s) => s.toLowerCase().trim();
}

/// ── Remote: gọi Edge Function `/home` (xem LO_TRINH_ANIME_APP.md §4) ──
class RemoteAnimeRepository implements AnimeRepository {
  final Dio dio;

  RemoteAnimeRepository(this.dio);

  @override
  Future<HomeFeed> loadHome() async {
    final r = await dio.get<Map<String, dynamic>>('/home');
    final data = (r.data?['data'] as Map?) ?? const {};
    return HomeFeed.fromJson(Map<String, dynamic>.from(data));
  }

  @override
  Future<List<Anime>> search(String query) async {
    final r = await dio.get<Map<String, dynamic>>(
      '/search',
      queryParameters: {'q': query},
    );
    final list = ((r.data?['data'] as Map?)?['items'] as List?) ?? const [];
    return list
        .map((e) => Anime.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
  }

  @override
  Future<Anime?> fetchAnime(String slug) async {
    try {
      final r = await dio.get<Map<String, dynamic>>(
        '/anime',
        queryParameters: {'slug': slug},
        // 404 = bộ này không có trong DB → trả null, không phải lỗi mạng
        options: Options(validateStatus: (s) => s == 200 || s == 404),
      );
      if (r.statusCode == 404) return null;
      final a = (r.data?['data'] as Map?)?['anime'];
      if (a is! Map) return null;
      return Anime.fromJson(Map<String, dynamic>.from(a));
    } on DioException catch (e) {
      if (e.response?.statusCode == 404) return null;
      rethrow;
    }
  }
}

// ── providers ─────────────────────────────────────────────
final animeRepositoryProvider = Provider<AnimeRepository>((ref) {
  if (!Env.hasBackend) return MockAnimeRepository();
  return RemoteAnimeRepository(
    Dio(BaseOptions(
      baseUrl: Env.apiBase,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 20),
      headers: {
        if (Env.anonKey.isNotEmpty) 'apikey': Env.anonKey,
        if (Env.anonKey.isNotEmpty) 'Authorization': 'Bearer ${Env.anonKey}',
      },
    )),
  );
});

/// 1 request duy nhất cho cả app — mọi screen dùng chung
final homeFeedProvider = FutureProvider<HomeFeed>((ref) async {
  return ref.watch(animeRepositoryProvider).loadHome();
});

/// Nơi lưu watchlist: mặc định SharedPreferences (bền, không cần đăng nhập).
/// Test/preview có thể override bằng `MemoryWatchlistStore()`.
final watchlistStoreProvider = Provider<WatchlistStore>((ref) {
  return PrefsWatchlistStore();
});

/// Watchlist = "Thư viện". Tự nạp lại danh sách đã lưu khi app mở, và ghi lại
/// mỗi lần thay đổi → tắt app mở lại vẫn còn (trước đây chỉ nằm trong RAM).
final watchlistProvider =
    StateNotifierProvider<WatchlistNotifier, Set<int>>((ref) {
  return WatchlistNotifier(ref.watch(watchlistStoreProvider));
});

class WatchlistNotifier extends StateNotifier<Set<int>> {
  final WatchlistStore store;

  WatchlistNotifier(this.store) : super(<int>{}) {
    ready = _hydrate();
  }

  /// Xong khi danh sách đã lưu trong máy được nạp vào `state`.
  /// Chỉ cần cho test — UI không phải chờ, vì `state` tự cập nhật.
  late final Future<void> ready;

  Future<void> _hydrate() async {
    try {
      final saved = await store.load();
      if (!mounted || saved.isEmpty) return;
      // Hợp nhất thay vì ghi đè: người dùng có thể đã bấm theo dõi trước khi
      // đọc xong bộ nhớ (đọc bất đồng bộ nên chuyện này là bình thường).
      final next = <int>{...saved, ...state};
      if (next.length == state.length) return;
      state = next;
      await store.save(next);
    } catch (_) {
      // không đọc được bộ nhớ → chạy tiếp với danh sách rỗng
    }
  }

  void toggle(int animeId) {
    final next = Set<int>.from(state);
    if (!next.remove(animeId)) next.add(animeId);
    state = next;
    unawaited(store.save(next));
  }

  bool contains(int animeId) => state.contains(animeId);
}

/// Chi tiết 1 bộ: ưu tiên dữ liệu đã có trong feed (0 request),
/// không có thì gọi `/anime?slug=` — nên deep link từ thông báo luôn mở được.
final animeDetailProvider =
    FutureProvider.family<Anime?, String>((ref, slug) async {
  if (slug.isEmpty) return null;

  final cached = ref.watch(homeFeedProvider).valueOrNull?.bySlug(slug);
  if (cached != null) return cached;

  return ref.watch(animeRepositoryProvider).fetchAnime(slug);
});

// tiện cho UI
extension FeedX on HomeFeed {
  Anime? firstFree() {
    for (final a in anime) {
      if (a.isFree) return a;
    }
    return anime.isEmpty ? null : anime.first;
  }
}
