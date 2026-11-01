import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../app/env.dart';
import '../core/models/anime.dart';
import '../core/models/home_feed.dart';
import 'mock_data.dart';

/// Hợp đồng dữ liệu — UI chỉ biết interface này, nên đổi backend không sửa UI.
abstract class AnimeRepository {
  Future<HomeFeed> loadHome();
  Future<List<Anime>> search(String query);
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

/// Watchlist tạm trong RAM (persist bằng Drift ở v1.1 — xem DECISION.md)
final watchlistProvider =
    StateNotifierProvider<WatchlistNotifier, Set<int>>((ref) {
  return WatchlistNotifier();
});

class WatchlistNotifier extends StateNotifier<Set<int>> {
  WatchlistNotifier() : super(<int>{});

  void toggle(int animeId) {
    final next = Set<int>.from(state);
    if (!next.remove(animeId)) next.add(animeId);
    state = next;
  }

  bool contains(int animeId) => state.contains(animeId);
}

// tiện cho UI
extension FeedX on HomeFeed {
  Anime? firstFree() {
    for (final a in anime) {
      if (a.isFree) return a;
    }
    return anime.isEmpty ? null : anime.first;
  }
}
