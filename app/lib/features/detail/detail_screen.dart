import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../app/theme.dart';
import '../../core/models/anime.dart';
import '../../core/models/episode_title.dart';
import '../../core/models/genre_vi.dart';
import '../../core/widgets/net_image.dart';
import '../../data/anime_repository.dart';

class DetailScreen extends ConsumerWidget {
  final String slug;
  const DetailScreen({super.key, required this.slug});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Ưu tiên dữ liệu đã có trong /home; nếu không có (deep link từ thông báo)
    // thì gọi /anime?slug= — xem `animeDetailProvider`.
    final detail = ref.watch(animeDetailProvider(slug));

    return Scaffold(
      body: detail.when(
        loading: () => const Center(
          child: CircularProgressIndicator(color: AppTheme.accent),
        ),
        error: (e, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'Không tải được thông tin anime.\n$e',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: AppTheme.muted, fontSize: 12),
                ),
                const SizedBox(height: 12),
                OutlinedButton(
                  onPressed: () =>
                      ref.invalidate(animeDetailProvider(slug)),
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
        data: (anime) {
          if (anime == null) {
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text('Không tìm thấy anime này',
                      style: TextStyle(color: AppTheme.muted, fontSize: 13)),
                  const SizedBox(height: 12),
                  OutlinedButton(
                    onPressed: () => context.canPop()
                        ? context.pop()
                        : context.go('/'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppTheme.text,
                      side: const BorderSide(color: AppTheme.line),
                    ),
                    child: const Text('Quay lại'),
                  ),
                ],
              ),
            );
          }
          return _DetailBody(anime: anime);
        },
      ),
    );
  }
}

class _DetailBody extends ConsumerWidget {
  final Anime anime;
  const _DetailBody({required this.anime});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final inList = ref.watch(watchlistProvider).contains(anime.id);
    final ep = anime.firstPlayable;
    // Danh sách tập đến từ 2 nguồn: lịch phát TMDB/AniList (biết đủ số tập)
    // và link YouTube official (chỉ một phần tập có bản phát). Hiện cả hai con
    // số để người dùng không bấm nhầm vào tập chưa phát được.
    final playableCount = anime.episodes.where((e) => e.playable).length;

    return CustomScrollView(
      slivers: [
        SliverAppBar(
          expandedHeight: 230,
          pinned: true,
          backgroundColor: AppTheme.bg,
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_rounded),
            onPressed: () => context.pop(),
          ),
          actions: [
            IconButton(
              tooltip: inList ? 'Bỏ theo dõi' : 'Theo dõi',
              icon: Icon(
                inList ? Icons.bookmark_rounded : Icons.bookmark_border_rounded,
                color: inList ? AppTheme.accent : AppTheme.text,
              ),
              onPressed: () {
                ref.read(watchlistProvider.notifier).toggle(anime.id);
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(inList
                        ? 'Đã bỏ "${anime.displayTitle}" khỏi thư viện'
                        : 'Đã thêm "${anime.displayTitle}" vào thư viện'),
                    duration: const Duration(seconds: 2),
                  ),
                );
              },
            ),
          ],
          flexibleSpace: FlexibleSpaceBar(
            background: Stack(
              fit: StackFit.expand,
              children: [
                NetImage(url: anime.banner ?? anime.cover),
                DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        AppTheme.bg.withAlpha(120),
                        AppTheme.bg.withAlpha(60),
                        AppTheme.bg,
                      ],
                      stops: const [0, 0.5, 1],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    NetImage(
                      url: anime.cover,
                      width: 96,
                      height: 140,
                      radius: BorderRadius.circular(10),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            anime.displayTitle,
                            style: const TextStyle(
                              fontSize: 19,
                              fontWeight: FontWeight.w800,
                              height: 1.2,
                              letterSpacing: -0.02,
                            ),
                          ),
                          if (anime.titleNative != null &&
                              anime.titleNative != anime.title)
                            Padding(
                              padding: const EdgeInsets.only(top: 3),
                              child: Text(
                                anime.titleNative!,
                                style: const TextStyle(
                                    fontSize: 11.5, color: AppTheme.muted),
                              ),
                            ),
                          const SizedBox(height: 8),
                          Wrap(
                            spacing: 6,
                            runSpacing: 6,
                            children: [
                              if (anime.score != null)
                                _meta('★ ${anime.score!.toStringAsFixed(1)}'),
                              if (anime.year != null) _meta('${anime.year}'),
                              if (anime.episodesTotal != null)
                                _meta('${anime.episodesTotal} tập'),
                              if (anime.format != null) _meta(anime.format!),
                              if (anime.status == 'RELEASING')
                                _meta('Đang chiếu', color: AppTheme.green),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),

                // ── nút xem ──
                if (ep != null)
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed: () => context.push(
                        '/watch?video=${ep.videoId}&title=${Uri.encodeComponent(anime.displayTitle)}',
                      ),
                      icon: const Icon(Icons.play_arrow_rounded),
                      label: Text('Xem tập ${ep.number} · miễn phí'),
                    ),
                  )
                else
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: AppTheme.surface,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: AppTheme.line),
                    ),
                    child: const Row(
                      children: [
                        Icon(Icons.info_outline_rounded,
                            size: 16, color: AppTheme.muted),
                        SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            'Bộ này chưa có bản phát miễn phí chính thức. '
                            'Xem trên nền tảng bên dưới.',
                            style: TextStyle(
                                fontSize: 11.5,
                                color: AppTheme.muted,
                                height: 1.4),
                          ),
                        ),
                      ],
                    ),
                  ),

                // ── nền tảng hợp pháp ──
                if (anime.platforms.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  const Text('Xem trên nền tảng chính thức',
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: AppTheme.muted)),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: anime.platforms
                        .map((p) => OutlinedButton.icon(
                              onPressed: () => _open(p.url),
                              icon: const Icon(Icons.open_in_new_rounded,
                                  size: 14),
                              label: Text(p.name,
                                  style: const TextStyle(fontSize: 12)),
                              style: OutlinedButton.styleFrom(
                                foregroundColor: AppTheme.text,
                                side: const BorderSide(color: AppTheme.line),
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 12, vertical: 8),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(8),
                                ),
                              ),
                            ))
                        .toList(),
                  ),
                ],

                // ── nội dung ──
                if (anime.synopsis.isNotEmpty) ...[
                  const SizedBox(height: 18),
                  Text(
                    anime.synopsis,
                    style: const TextStyle(
                      fontSize: 12.8,
                      height: 1.62,
                      color: Color(0xFFC3CBDC),
                    ),
                  ),
                ],

                if (anime.genres.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: anime.genres
                        .map((g) => Chip(
                              label: Text(genreVi(g)),
                              visualDensity: VisualDensity.compact,
                              materialTapTargetSize:
                                  MaterialTapTargetSize.shrinkWrap,
                            ))
                        .toList(),
                  ),
                ],

                // ── danh sách tập ──
                if (anime.episodes.isNotEmpty) ...[
                  const SizedBox(height: 20),
                  Wrap(
                    crossAxisAlignment: WrapCrossAlignment.center,
                    spacing: 8,
                    children: [
                      Text(
                        'Tập phim (${anime.episodes.length})',
                        style: const TextStyle(
                            fontSize: 14, fontWeight: FontWeight.w700),
                      ),
                      if (playableCount > 0)
                        Text(
                          '· $playableCount tập xem được',
                          style: const TextStyle(
                              fontSize: 11.5, color: AppTheme.green),
                        )
                      else
                        const Text(
                          '· chưa có bản phát miễn phí',
                          style: TextStyle(
                              fontSize: 11.5, color: AppTheme.muted),
                        ),
                    ],
                  ),
                  const SizedBox(height: 10),
                ],
              ],
            ),
          ),
        ),
        SliverPadding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          sliver: SliverGrid.builder(
            // Trước đây là 4 cột cố định → trên desktop (Chrome) mỗi ô rộng
            // ~370px và cao ~270px, chỉ có một con số ở giữa: nhìn như ô trống.
            // MaxCrossAxisExtent giữ ô luôn ~150–170px ở mọi bề rộng màn hình.
            gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
              maxCrossAxisExtent: 168,
              mainAxisSpacing: 8,
              crossAxisSpacing: 8,
              childAspectRatio: 1.1,
            ),
            itemCount: anime.episodes.length,
            itemBuilder: (context, i) {
              final e = anime.episodes[i];
              return InkWell(
                borderRadius: BorderRadius.circular(9),
                onTap: () {
                  if (e.playable) {
                    context.push(
                      '/watch?video=${e.videoId}&title=${Uri.encodeComponent('${anime.displayTitle} · Tập ${e.number}')}',
                    );
                  } else {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(e.airingAt == null
                            ? 'Tập ${e.number} chưa có bản phát chính thức'
                            : e.airingAt!.isAfter(DateTime.now())
                                ? 'Tập ${e.number} chiếu sau '
                                    '${VnTime.countdown(e.airingAt!)}'
                                : 'Tập ${e.number} đã chiếu nhưng app chưa có '
                                    'bản phát miễn phí chính thức'),
                      ),
                    );
                  }
                },
                child: Container(
                  decoration: BoxDecoration(
                    color: AppTheme.surface2,
                    borderRadius: BorderRadius.circular(9),
                    border: Border.all(
                      color: e.playable ? AppTheme.accent.withAlpha(90) : AppTheme.line,
                    ),
                  ),
                  alignment: Alignment.center,
                  padding: const EdgeInsets.symmetric(
                      horizontal: 6, vertical: 8),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        e.number == 0 ? 'FULL' : '${e.number}',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w800,
                          color: e.playable ? AppTheme.text : AppTheme.muted,
                        ),
                      ),
                      // Tên tập lấy từ TMDB (language=vi-VN). TMDB hay trả
                      // placeholder "Episode 7" → lọc bỏ, xem episode_title.dart.
                      if (displayEpisodeTitle(e.title, e.number) != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 3),
                          child: Text(
                            displayEpisodeTitle(e.title, e.number)!,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              fontSize: 9,
                              height: 1.25,
                              color: AppTheme.muted,
                            ),
                          ),
                        ),
                      if (e.playable)
                        const Padding(
                          padding: EdgeInsets.only(top: 4),
                          child: Text('▶ xem được',
                              style: TextStyle(
                                  fontSize: 8.5, color: AppTheme.accent)),
                        )
                      else if (e.airingAt != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(
                            VnTime.airStatus(e.airingAt!),
                            style: const TextStyle(
                                fontSize: 8.5, color: AppTheme.muted),
                          ),
                        ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
        const SliverToBoxAdapter(child: SizedBox(height: 50)),
      ],
    );
  }

  Widget _meta(String text, {Color? color}) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: AppTheme.surface2,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: AppTheme.line),
        ),
        child: Text(
          text,
          style: TextStyle(
            fontSize: 10.5,
            fontWeight: FontWeight.w600,
            color: color ?? AppTheme.text,
          ),
        ),
      );

  Future<void> _open(String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }
}
