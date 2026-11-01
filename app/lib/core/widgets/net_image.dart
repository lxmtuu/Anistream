import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../../app/theme.dart';

/// Ảnh mạng có cache + placeholder + fallback.
/// Dùng cached_network_image để tiết kiệm data người dùng (quan trọng ở VN).
class NetImage extends StatelessWidget {
  final String? url;
  final double? width;
  final double? height;
  final BoxFit fit;
  final BorderRadius? radius;

  const NetImage({
    super.key,
    required this.url,
    this.width,
    this.height,
    this.fit = BoxFit.cover,
    this.radius,
  });

  @override
  Widget build(BuildContext context) {
    Widget img;
    if (url == null || url!.isEmpty) {
      img = _fallback();
    } else {
      img = CachedNetworkImage(
        imageUrl: url!,
        width: width,
        height: height,
        fit: fit,
        fadeInDuration: const Duration(milliseconds: 180),
        placeholder: (_, __) => _placeholder(),
        errorWidget: (_, __, ___) => _fallback(),
      );
    }
    if (radius == null) return img;
    return ClipRRect(borderRadius: radius!, child: img);
  }

  Widget _placeholder() => Container(
        width: width,
        height: height,
        color: AppTheme.surface2,
      );

  Widget _fallback() => Container(
        width: width,
        height: height,
        color: AppTheme.surface2,
        alignment: Alignment.center,
        child: const Icon(Icons.movie_outlined, color: AppTheme.muted, size: 22),
      );
}
