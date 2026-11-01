import 'package:flutter/material.dart';

import '../../app/theme.dart';
import '../models/anime.dart';
import 'net_image.dart';

/// Poster dọc dùng trong shelf ngang (kiểu Netflix).
class AnimeCard extends StatelessWidget {
  final Anime anime;
  final VoidCallback onTap;
  final double width;

  const AnimeCard({
    super.key,
    required this.anime,
    required this.onTap,
    this.width = 116,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: width,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Stack(
              children: [
                NetImage(
                  url: anime.cover,
                  width: width,
                  height: width * 1.45,
                  radius: BorderRadius.circular(10),
                ),
                if (anime.isFree)
                  Positioned(
                    top: 6,
                    left: 6,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: AppTheme.green,
                        borderRadius: BorderRadius.circular(5),
                      ),
                      child: const Text(
                        'FREE',
                        style: TextStyle(
                          fontSize: 9,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFF06281B),
                        ),
                      ),
                    ),
                  ),
                if (anime.score != null)
                  Positioned(
                    bottom: 6,
                    right: 6,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 5, vertical: 2),
                      decoration: BoxDecoration(
                        color: Colors.black.withAlpha(170),
                        borderRadius: BorderRadius.circular(5),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.star_rounded,
                              size: 11, color: Color(0xFFFFD166)),
                          const SizedBox(width: 2),
                          Text(
                            anime.score!.toStringAsFixed(1),
                            style: const TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              anime.displayTitle,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 11.5,
                height: 1.25,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
