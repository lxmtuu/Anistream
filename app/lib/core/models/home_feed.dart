import 'anime.dart';

/// Toàn bộ payload của 1 lần gọi `/home`.
/// App chỉ gọi 1 API duy nhất khi mở → mở nhanh, tiết kiệm pin/data.
///
/// Lưu ý kỹ thuật: KHÔNG dùng `const` constructor ở đây.
/// Dart không cho phép trường `late final` (hoặc tính toán) trong class có const
/// constructor — đó là lỗi biên dịch. Index `byId` vì thế được tính lazy qua getter.
class HomeFeed {
  final DateTime generatedAt;
  final List<Anime> anime;
  final List<Shelf> shelves;
  final List<ScheduleSlot> schedule;

  HomeFeed({
    required this.generatedAt,
    required this.anime,
    required this.shelves,
    required this.schedule,
  });

  // cache index id → Anime, tính 1 lần khi cần
  Map<int, Anime>? _byIdCache;

  Map<int, Anime> get byId =>
      _byIdCache ??= {for (final a in anime) a.id: a};

  Anime? animeOf(int id) => byId[id];

  /// Mở shelf ra danh sách anime (bỏ id không tồn tại)
  List<Anime> itemsOf(Shelf s) =>
      s.ids.map(animeOf).whereType<Anime>().toList();

  Anime? bySlug(String slug) {
    for (final a in anime) {
      if (a.slug == slug) return a;
    }
    return null;
  }

  factory HomeFeed.fromJson(Map<String, dynamic> j) => HomeFeed(
        generatedAt:
            DateTime.tryParse((j['generated_at'] as String?) ?? '')?.toLocal() ??
                DateTime.now(),
        anime: ((j['anime'] as List?) ?? const [])
            .map((e) => Anime.fromJson(e as Map<String, dynamic>))
            .toList(),
        shelves: ((j['shelves'] as List?) ?? const [])
            .map((e) => Shelf.fromJson(e as Map<String, dynamic>))
            .toList(),
        schedule: ((j['schedule'] as List?) ?? const [])
            .map((e) => ScheduleSlot.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}
