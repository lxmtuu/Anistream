import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app/router.dart';
import 'app/theme.dart';
import 'core/push/push_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // Bật push ở nền: nếu chưa `flutterfire configure` thì tự bỏ qua, app vẫn chạy.
  // Bấm vào thông báo "Tập N vừa phát" → mở đúng /anime/<slug>.
  PushService.instance.init(
    onRouteFromNotification: (route) {
      try {
        appRouter.push(route);
      } catch (e) {
        debugPrint('router chưa sẵn sàng: $e');
      }
    },
  );

  runApp(const ProviderScope(child: AniStreamApp()));
}

class AniStreamApp extends StatelessWidget {
  const AniStreamApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'AniStream',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark(),
      routerConfig: appRouter,
    );
  }
}
