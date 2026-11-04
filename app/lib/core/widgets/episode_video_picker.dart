import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme.dart';
import '../models/anime.dart';

/// Mở video official của episode; nếu có nhiều phiên bản thì để người dùng chọn.
Future<void> playEpisode(
  BuildContext context,
  Anime anime,
  Episode episode,
) async {
  final choices = episode.videoOptions.isNotEmpty
      ? episode.videoOptions
      : [
          EpisodeVideoOption(
            videoId: episode.videoId!,
            platform: episode.platform ?? 'YouTube',
            label: 'Phát video',
          ),
        ];

  var selected = choices.first;
  if (choices.length > 1) {
    final choice = await showModalBottomSheet<EpisodeVideoOption>(
      context: context,
      backgroundColor: AppTheme.surface2,
      builder: (sheetContext) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text(
                'Chọn bản phát',
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  color: AppTheme.text,
                ),
              ),
            ),
            for (final option in choices)
              ListTile(
                leading: const Icon(Icons.play_circle_outline,
                    color: AppTheme.accent),
                title: Text(
                  option.label,
                  style: const TextStyle(color: AppTheme.text),
                ),
                subtitle: Text(
                  option.platform,
                  style: const TextStyle(color: AppTheme.muted, fontSize: 12),
                ),
                onTap: () => Navigator.of(sheetContext).pop(option),
              ),
          ],
        ),
      ),
    );
    if (choice == null || !context.mounted) return;
    selected = choice;
  }

  final episodeLabel = episode.number == 0 ? 'Cả bộ' : 'Tập ${episode.number}';
  final title = '${anime.displayTitle} · $episodeLabel · ${selected.label}';
  context.push(
    '/watch?video=${selected.videoId}&title=${Uri.encodeComponent(title)}',
  );
}
