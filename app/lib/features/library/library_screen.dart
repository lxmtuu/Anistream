import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme.dart';
import '../../core/models/anime.dart';
import '../../core/widgets/net_image.dart';
import '../../data/anime_repository.dart';

/// Thư viện = watchlist.
///
/// Danh sách ID lưu **bền trên máy** (`WatchlistStore` → SharedPreferences) nên
/// tắt app mở lại vẫn còn; phần tên/poster lấy từ feed `/home`. Đổi sang Drift
/// hoặc đồng bộ Supabase chỉ cần thay implementation của `WatchlistStore`.
class LibraryScreen extends ConsumerWidget {
  const LibraryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ids = ref.watch(watchlistProvider);
    final feed = ref.watch(homeFeedProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Thư viện',
            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
        actions: [
          if (ids.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(right: 16),
              child: Center(
                child: Text(
                  '${ids.length} bộ',
                  style:
                      const TextStyle(fontSize: 12, color: AppTheme.muted),
                ),
              ),
            ),
        ],
      ),
      // Thư viện lưu trên máy: chỉ phần TÊN/POSTER mới cần tải từ mạng.
      body: feed.when(
        loading: () => const Center(
            child: CircularProgressIndicator(color: AppTheme.accent)),
        error: (e, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(28),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  ids.isEmpty
                      ? 'Không tải được dữ liệu.\n$e'
                      : 'Bạn đang theo dõi ${ids.length} bộ nhưng chưa tải được '
                          'tên và poster.\n$e',
                  textAlign: TextAlign.center,
                  style:
                      const TextStyle(fontSize: 12, color: AppTheme.muted),
                ),
                const SizedBox(height: 12),
                OutlinedButton(
                  onPressed: () => ref.invalidate(homeFeedProvider),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppTheme.text,
                    side: const BorderSide(color: AppTheme.line),
                  ),
                  child: const Text('Thử lại'),
                ),
              ],
            ),
          ),
        ),
        data: (data) {
          final items = ids
              .map(data.animeOf)
              .whereType<Anime>()
              .toList();

          // Có theo dõi nhưng catalog chưa trả về bộ nào trong số đó
          // (bộ bị gỡ, hoặc feed chỉ chứa 1 phần catalog) — không được hiện
          // "Thư viện trống" vì như vậy là nói sai với người dùng.
          if (ids.isNotEmpty && items.isEmpty) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: Text(
                  'Đang theo dõi ${ids.length} bộ nhưng chưa bộ nào có trong '
                  'danh mục tải về. Kéo lại sau hoặc mở từng bộ để xem lại.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                      fontSize: 12, color: AppTheme.muted, height: 1.6),
                ),
              ),
            );
          }

          if (items.isEmpty) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(Icons.bookmark_border_rounded,
                        size: 44, color: AppTheme.muted),
                    const SizedBox(height: 14),
                    const Text('Thư viện trống',
                        style: TextStyle(
                            fontSize: 14, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 6),
                    const Text(
                      'Bấm 🔖 ở trang chi tiết để theo dõi anime.\n'
                      'Danh sách lưu ngay trên máy — không cần đăng nhập,\n'
                      'tắt app mở lại vẫn còn.',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                          fontSize: 12, color: AppTheme.muted, height: 1.6),
                    ),
                    const SizedBox(height: 18),
                    OutlinedButton(
                      onPressed: () => context.go('/'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppTheme.text,
                        side: const BorderSide(color: AppTheme.line),
                      ),
                      child: const Text('Khám phá anime'),
                    ),
                  ],
                ),
              ),
            );
          }

          return ListView.separated(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 90),
            itemCount: items.length,
            separatorBuilder: (_, __) =>
                const Divider(color: AppTheme.line, height: 1),
            itemBuilder: (context, i) {
              final a = items[i];
              return ListTile(
                contentPadding: EdgeInsets.zero,
                onTap: () => context.push('/anime/${a.slug}'),
                leading: NetImage(
                  url: a.cover,
                  width: 42,
                  height: 60,
                  radius: BorderRadius.circular(6),
                ),
                title: Text(a.displayTitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 13, fontWeight: FontWeight.w600)),
                subtitle: Text(
                  '${a.episodes.length} tập · ${a.isFree ? "có bản miễn phí" : "nền tảng khác"}',
                  style: const TextStyle(fontSize: 11, color: AppTheme.muted),
                ),
                trailing: IconButton(
                  icon: const Icon(Icons.bookmark_remove_rounded,
                      size: 18, color: AppTheme.muted),
                  onPressed: () =>
                      ref.read(watchlistProvider.notifier).toggle(a.id),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
