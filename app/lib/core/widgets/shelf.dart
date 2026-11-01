import 'package:flutter/material.dart';

import '../../app/theme.dart';
import '../models/anime.dart';
import 'anime_card.dart';

/// Một hàng poster cuộn ngang. `ListView.builder` để chỉ build cái đang thấy.
class AnimeShelf extends StatelessWidget {
  final String title;
  final List<Anime> items;
  final void Function(Anime) onTap;
  final String? actionLabel;
  final VoidCallback? onAction;

  const AnimeShelf({
    super.key,
    required this.title,
    required this.items,
    required this.onTap,
    this.actionLabel,
    this.onAction,
  });

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 20, 8, 10),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(
                    fontSize: 14.5,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.01,
                  ),
                ),
              ),
              if (actionLabel != null)
                TextButton(
                  onPressed: onAction,
                  child: Text(
                    actionLabel!,
                    style: const TextStyle(
                        fontSize: 12, color: AppTheme.muted),
                  ),
                ),
            ],
          ),
        ),
        SizedBox(
          height: 116 * 1.45 + 34,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            itemCount: items.length,
            separatorBuilder: (_, __) => const SizedBox(width: 10),
            itemBuilder: (context, i) => AnimeCard(
              anime: items[i],
              onTap: () => onTap(items[i]),
            ),
          ),
        ),
      ],
    );
  }
}

/// Skeleton khi đang tải — giữ đúng layout để không bị "nhảy" khi có data.
class ShelfSkeleton extends StatelessWidget {
  const ShelfSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    Widget box(double w, double h) => Container(
          width: w,
          height: h,
          decoration: BoxDecoration(
            color: AppTheme.surface2,
            borderRadius: BorderRadius.circular(10),
          ),
        );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 20, 16, 12),
          child: box(150, 14),
        ),
        SizedBox(
          height: 116 * 1.45,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            itemCount: 5,
            separatorBuilder: (_, __) => const SizedBox(width: 10),
            itemBuilder: (_, __) => box(116, 116 * 1.45),
          ),
        ),
      ],
    );
  }
}
