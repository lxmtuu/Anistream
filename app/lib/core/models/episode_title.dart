/// Lọc tên tập "rác" trước khi hiển thị.
///
/// TMDB trả placeholder khi tập chưa có bản dịch: `Episode 7`, `Ep. 7`, `Tập 7`,
/// `第7話`. Đo trên DB thật: **429/526** tên tập là dạng này → app hiện một dòng
/// chữ vô nghĩa ngay dưới con số to của ô tập.
///
/// Lọc ở tầng hiển thị (không chỉ ở ingest) để dữ liệu CŨ đã ghi vẫn hiện đúng,
/// không phải chạy lại job D mới hết.
library;

final RegExp _generic = RegExp(
  r'^\s*(?:episode|ep\.?|tập|tap|第)?\s*\d+\s*(?:話|话|集)?\s*$',
  caseSensitive: false,
);

/// Trả tên tập để hiện, hoặc `null` nếu là placeholder / rỗng.
String? displayEpisodeTitle(String title, int number) {
  final t = title.trim();
  if (t.isEmpty) return null;
  if (_generic.hasMatch(t)) return null;
  return t;
}
