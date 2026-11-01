import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme.dart';
import '../../core/models/anime.dart';
import '../../core/widgets/net_image.dart';
import '../../data/anime_repository.dart';

/// Thư viện = watchlist. v1 lưu trong RAM; v1.1 chuyển sang Drift (SQLite)
/// để offline và đồng bộ — xem DECISION.md.
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
      ),
      body: feed.when(
        loading: () => const Center(
            child: CircularProgressIndicator(color: AppTheme.accent)),
        error: (e, _) => Center(child: Text('$e')),
        data: (data) {
          final items = ids
              .map(data.animeOf)
              .whereType<Anime>()
              .toList();

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
                      'Khi có tập mới, bạn sẽ nhận thông báo (v1.1).',
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
