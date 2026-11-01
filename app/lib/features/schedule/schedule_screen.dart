import 'dart:ui' show FontFeature;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme.dart';
import '../../core/models/anime.dart';
import '../../core/widgets/net_image.dart';
import '../../data/anime_repository.dart';

/// Lịch phát — "trái tim" của app: cho người dùng biết tập mới ra lúc nào.
class ScheduleScreen extends ConsumerWidget {
  const ScheduleScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final feed = ref.watch(homeFeedProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Lịch phát',
            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
      ),
      body: feed.when(
        loading: () => const Center(
            child: CircularProgressIndicator(color: AppTheme.accent)),
        error: (e, _) => Center(
          child: Text('$e',
              style: const TextStyle(color: AppTheme.muted, fontSize: 12)),
        ),
        data: (data) {
          final slots = [...data.schedule]
            ..sort((a, b) => a.airingAt.compareTo(b.airingAt));

          // nhóm theo ngày
          final groups = <String, List<ScheduleSlot>>{};
          for (final s in slots) {
            groups.putIfAbsent(VnTime.dayLabel(s.airingAt), () => []).add(s);
          }
          if (groups.isEmpty) {
            return const Center(
                child: Text('Chưa có lịch phát',
                    style: TextStyle(color: AppTheme.muted)));
          }

          return ListView(
            padding: const EdgeInsets.fromLTRB(0, 4, 0, 90),
            children: [
              for (final entry in groups.entries) ...[
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                  child: Text(
                    entry.key,
                    style: const TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w800,
                      color: AppTheme.accent,
                      letterSpacing: 0.3,
                    ),
                  ),
                ),
                for (final slot in entry.value)
                  _SlotTile(
                    slot: slot,
                    anime: data.animeOf(slot.animeId),
                  ),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _SlotTile extends StatelessWidget {
  final ScheduleSlot slot;
  final Anime? anime;
  const _SlotTile({required this.slot, this.anime});

  @override
  Widget build(BuildContext context) {
    final a = anime;
    if (a == null) return const SizedBox.shrink();
    final isPast = slot.airingAt.isBefore(DateTime.now());

    return InkWell(
      onTap: () => context.push('/anime/${a.slug}'),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 7, 16, 7),
        child: Row(
          children: [
            SizedBox(
              width: 44,
              child: Text(
                VnTime.hhmm(slot.airingAt),
                style: TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w700,
                  color: isPast ? AppTheme.muted : AppTheme.text,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
            ),
            NetImage(
              url: a.cover,
              width: 40,
              height: 56,
              radius: BorderRadius.circular(6),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    a.displayTitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 12.8,
                      fontWeight: FontWeight.w600,
                      color: isPast ? AppTheme.muted : AppTheme.text,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'Tập ${slot.episode} · ${VnTime.countdown(slot.airingAt)}',
                    style: const TextStyle(
                        fontSize: 10.5, color: AppTheme.muted),
                  ),
                ],
              ),
            ),
            if (a.isFree)
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: AppTheme.green.withAlpha(38),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: const Text(
                  'FREE',
                  style: TextStyle(
                    fontSize: 8.5,
                    fontWeight: FontWeight.w800,
                    color: AppTheme.green,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
