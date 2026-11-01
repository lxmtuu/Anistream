import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/push/push_service.dart';
import '../../data/anime_repository.dart';
import '../home/home_screen.dart';
import '../library/library_screen.dart';
import '../schedule/schedule_screen.dart';
import '../search/search_screen.dart';

/// 4 tab chính. Dùng IndexedStack để giữ state từng tab (không reload khi đổi tab).
class RootScreen extends ConsumerStatefulWidget {
  final int initialIndex;
  const RootScreen({super.key, this.initialIndex = 0});

  @override
  ConsumerState<RootScreen> createState() => _RootScreenState();
}

class _RootScreenState extends ConsumerState<RootScreen> {
  late int _index = widget.initialIndex;

  static const _pages = [
    HomeScreen(),
    ScheduleScreen(),
    SearchScreen(),
    LibraryScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    // Watchlist thay đổi → đồng bộ danh sách bộ muốn nhận thông báo lên backend.
    // Đây là toàn bộ "cài đặt thông báo" của người dùng: theo dõi bộ nào thì
    // nhận tin tập mới của bộ đó.
    ref.listen<Set<int>>(watchlistProvider, (previous, next) {
      PushService.instance.syncSubscriptions(next);
    });

    return Scaffold(
      body: IndexedStack(index: _index, children: _pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        height: 62,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home_rounded),
            label: 'Trang chủ',
          ),
          NavigationDestination(
            icon: Icon(Icons.calendar_month_outlined),
            selectedIcon: Icon(Icons.calendar_month_rounded),
            label: 'Lịch phát',
          ),
          NavigationDestination(
            icon: Icon(Icons.search_rounded),
            selectedIcon: Icon(Icons.search_rounded),
            label: 'Tìm',
          ),
          NavigationDestination(
            icon: Icon(Icons.bookmark_border_rounded),
            selectedIcon: Icon(Icons.bookmark_rounded),
            label: 'Thư viện',
          ),
        ],
      ),
    );
  }
}
