/// Nhãn thể loại tiếng Việt.
///
/// Vì sao cần: AniList trả `genres` bằng tiếng Anh ("Comedy", "Slice of Life"),
/// nên trang chi tiết hiện chip tiếng Anh giữa một app toàn tiếng Việt.
/// Giữ nguyên khoá gốc trong DB/API, chỉ đổi nhãn lúc hiển thị — như vậy không
/// phải migrate dữ liệu và vẫn khớp khi sau này thêm bộ lọc theo thể loại.
library;

const Map<String, String> _genreVi = {
  'Action': 'Hành động',
  'Adventure': 'Phiêu lưu',
  'Comedy': 'Hài',
  'Drama': 'Chính kịch',
  'Ecchi': 'Ecchi',
  'Fantasy': 'Kỳ ảo',
  'Horror': 'Kinh dị',
  'Mahou Shoujo': 'Phép thuật thiếu nữ',
  'Mecha': 'Mecha',
  'Music': 'Âm nhạc',
  'Mystery': 'Bí ẩn',
  'Psychological': 'Tâm lý',
  'Romance': 'Lãng mạn',
  'Sci-Fi': 'Khoa học viễn tưởng',
  'Slice of Life': 'Đời thường',
  'Sports': 'Thể thao',
  'Supernatural': 'Siêu nhiên',
  'Thriller': 'Giật gân',
  'Isekai': 'Chuyển sinh',
  'Gourmet': 'Ẩm thực',
  'School': 'Học đường',
  'Shounen': 'Shounen',
  'Seinen': 'Seinen',
  'Shoujo': 'Shoujo',
  'Josei': 'Josei',
  'Kids': 'Thiếu nhi',
};

/// Trả nhãn tiếng Việt; thể loại lạ thì giữ nguyên (không bao giờ trả rỗng).
String genreVi(String genre) {
  final key = genre.trim();
  return _genreVi[key] ?? key;
}
