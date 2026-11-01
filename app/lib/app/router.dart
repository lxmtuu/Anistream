import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../features/detail/detail_screen.dart';
import '../features/player/player_screen.dart';
import '../features/root/root_screen.dart';

/// Deep link: anistream://anime/<slug>
/// Khi có tên miền riêng, thêm Universal Links / App Links (xem README).
final GoRouter appRouter = GoRouter(
  initialLocation: '/',
  routes: [
    GoRoute(
      path: '/',
      builder: (context, state) => const RootScreen(),
    ),
    // tab Lịch phát / Tìm / Thư viện có thể mở trực tiếp từ deep link
    GoRoute(
      path: '/schedule',
      builder: (context, state) => const RootScreen(initialIndex: 1),
    ),
    GoRoute(
      path: '/search',
      builder: (context, state) => const RootScreen(initialIndex: 2),
    ),
    GoRoute(
      path: '/library',
      builder: (context, state) => const RootScreen(initialIndex: 3),
    ),
    GoRoute(
      path: '/anime/:slug',
      builder: (context, state) =>
          DetailScreen(slug: state.pathParameters['slug'] ?? ''),
    ),
    GoRoute(
      path: '/watch',
      builder: (context, state) {
        final videoId = state.uri.queryParameters['video'] ?? '';
        final title = state.uri.queryParameters['title'] ?? 'Đang phát';
        if (videoId.isEmpty) {
          return const Scaffold(
            body: Center(child: Text('Thiếu video ID')),
          );
        }
        return PlayerScreen(videoId: videoId, title: title);
      },
    ),
  ],
  errorBuilder: (context, state) => Scaffold(
    appBar: AppBar(),
    body: Center(child: Text('Không tìm thấy: ${state.uri}')),
  ),
);
