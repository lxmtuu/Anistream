import 'package:anistream/data/anime_repository.dart';
import 'package:anistream/data/watchlist_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Test "Thư viện bền qua lần mở app". Chạy: `cd app && flutter test`
/// Không cần mạng, không cần backend, không cần thiết bị.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('PrefsWatchlistStore', () {
    test('lưu rồi đọc lại đúng danh sách', () async {
      SharedPreferences.setMockInitialValues({});
      final store = PrefsWatchlistStore();

      expect(await store.load(), isEmpty);
      await store.save({154587, 21, 9});
      expect(await store.load(), {154587, 21, 9});
    });

    test('dữ liệu hỏng → trả rỗng thay vì crash', () async {
      SharedPreferences.setMockInitialValues(
        {PrefsWatchlistStore.key: 'không-phải-json'},
      );
      expect(await PrefsWatchlistStore().load(), isEmpty);
    });

    test('chấp nhận số dạng chuỗi (dữ liệu cũ) và bỏ giá trị lạ', () async {
      SharedPreferences.setMockInitialValues(
        {PrefsWatchlistStore.key: '["7", 9, null, {"x":1}]'},
      );
      expect(await PrefsWatchlistStore().load(), {7, 9});
    });
  });

  group('WatchlistNotifier', () {
    test('nạp danh sách đã lưu khi khởi động', () async {
      final store = MemoryWatchlistStore({42});
      final notifier = WatchlistNotifier(store);
      await notifier.ready;

      expect(notifier.state, {42});
      expect(notifier.contains(42), isTrue);
    });

    test('toggle ghi ngay xuống store', () async {
      final store = MemoryWatchlistStore({42});
      final notifier = WatchlistNotifier(store);
      await notifier.ready;

      notifier.toggle(7);
      notifier.toggle(42); // bỏ theo dõi
      await Future<void>.delayed(Duration.zero);

      expect(notifier.state, {7});
      expect(await store.load(), {7});
    });

    test('thao tác trước khi đọc xong bộ nhớ không bị ghi đè', () async {
      final store = MemoryWatchlistStore({1, 2});
      final notifier = WatchlistNotifier(store);

      // người dùng bấm theo dõi ngay khi app vừa mở (chưa hydrate xong)
      notifier.toggle(3);
      await notifier.ready;

      expect(notifier.state, {1, 2, 3});
      expect(await store.load(), {1, 2, 3});
    });
  });
}
