import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme.dart';
import '../../core/models/anime.dart';
import '../../core/models/home_feed.dart';
import '../../core/widgets/net_image.dart';
import '../../core/widgets/shelf.dart';
import '../../data/anime_repository.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final feed = ref.watch(homeFeedProvider);

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: feed.when(
          loading: () => ListView(
            children: const [
              _HeroSkeleton(),
              ShelfSkeleton(),
              ShelfSkeleton(),
            ],
          ),
          error: (e, _) => _ErrorState(
            message: '$e',
            onRetry: () => ref.invalidate(homeFeedProvider),
          ),
          data: (data) => RefreshIndicator(
            color: AppTheme.accent,
            backgroundColor: AppTheme.surface,
            onRefresh: () async {
              ref.invalidate(homeFeedProvider);
              await ref.read(homeFeedProvider.future);
            },
            child: _HomeBody(feed: data),
          ),
        ),
      ),
    );
  }
}

class _HomeBody extends StatelessWidget {
  final HomeFeed feed;
  const _HomeBody({required this.feed});

  @override
  Widget build(BuildContext context) {
    final hero = feed.firstFree();
    final shelves = feed.shelves
        .where((s) => s.kind != 'free' || s.ids.isNotEmpty)
        .toList();

    return CustomScrollView(
      slivers: [
        if (hero != null) SliverToBoxAdapter(child: _Hero(anime: hero)),
        SliverList.builder(
          itemCount: shelves.length,
          itemBuilder: (context, i) {
            final s = shelves[i];
            return AnimeShelf(
              title: s.title,
              items: feed.itemsOf(s),
              onTap: (a) => context.push('/anime/${a.slug}'),
              actionLabel: i == 0 ? 'Tất cả' : null,
              onAction: i == 0
                  ? () => context.go('/schedule')
                  : null,
            );
          },
        ),
        const SliverToBoxAdapter(
          child: Padding(
            padding: EdgeInsets.fromLTRB(16, 26, 16, 8),
            child: Text(
              'Video do các kênh chính thức đăng công khai, phát qua trình phát '
              'YouTube chính thức. AniStream không lưu trữ video.',
              style: TextStyle(fontSize: 10.5, color: AppTheme.muted, height: 1.5),
            ),
          ),
        ),
        const SliverToBoxAdapter(child: SizedBox(height: 90)),
      ],
    );
  }
}

class _Hero extends StatelessWidget {
  final Anime anime;
  const _Hero({required this.anime});

  @override
  Widget build(BuildContext context) {
    final next = anime.nextEpisode;
    return Stack(
      children: [
        NetImage(
          url: anime.banner ?? anime.cover,
          width: double.infinity,
          height: 340,
        ),
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  AppTheme.bg.withAlpha(90),
                  AppTheme.bg.withAlpha(120),
                  AppTheme.bg,
                ],
                stops: const [0.0, 0.55, 1.0],
              ),
            ),
          ),
        ),
        Positioned(
          left: 16,
          right: 16,
          bottom: 18,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  if (anime.isFree)
                    _pill('MIỄN PHÍ · HỢP PHÁP', AppTheme.green,
                        const Color(0xFF06281B)),
                  if (anime.score != null) ...[
                    const SizedBox(width: 6),
                    _pill('★ ${anime.score!.toStringAsFixed(1)}',
                        AppTheme.surface2, AppTheme.text),
                  ],
                ],
              ),
              const SizedBox(height: 10),
              Text(
                anime.displayTitle,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w800,
                  height: 1.15,
                  letterSpacing: -0.02,
                ),
              ),
              if (next != null) ...[
                const SizedBox(height: 6),
                Text(
                  next.airingAt == null
                      ? 'Có ${anime.episodes.length} tập xem được'
                      : 'Tập ${next.number} · ${VnTime.countdown(next.airingAt!)}',
                  style: const TextStyle(fontSize: 12, color: AppTheme.muted),
                ),
              ],
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: () {
                        final ep = anime.firstPlayable;
                        if (ep != null) {
                          context.push(
                            '/watch?video=${ep.videoId}&title=${Uri.encodeComponent(anime.displayTitle)}',
                          );
                        } else {
                          context.push('/anime/${anime.slug}');
                        }
                      },
                      icon: const Icon(Icons.play_arrow_rounded, size: 20),
                      label: Text(anime.firstPlayable != null
                          ? 'Xem ngay'
                          : 'Xem chi tiết'),
                    ),
                  ),
                  const SizedBox(width: 10),
                  OutlinedButton(
                    onPressed: () => context.push('/anime/${anime.slug}'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppTheme.text,
                      side: const BorderSide(color: AppTheme.line),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 16, vertical: 14),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                    ),
                    child: const Text('Chi tiết'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _pill(String text, Color bg, Color fg) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(5),
        ),
        child: Text(
          text,
          style: TextStyle(
            fontSize: 9.5,
            fontWeight: FontWeight.w800,
            letterSpacing: 0.4,
            color: fg,
          ),
        ),
      );
}

class _HeroSkeleton extends StatelessWidget {
  const _HeroSkeleton();

  @override
  Widget build(BuildContext context) => Container(
        height: 340,
        color: AppTheme.surface2,
      );
}

class _ErrorState extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _ErrorState({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.cloud_off_rounded, size: 42, color: AppTheme.muted),
            const SizedBox(height: 12),
            const Text('Không tải được dữ liệu',
                style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Text(
              message,
              textAlign: TextAlign.center,
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 11.5, color: AppTheme.muted),
            ),
            const SizedBox(height: 16),
            FilledButton(onPressed: onRetry, child: const Text('Thử lại')),
          ],
        ),
      ),
    );
  }
}
