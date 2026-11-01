/// Đếm tập để hiển thị ĐÚNG.
///
/// API trả kèm một entry `number == 0` cho "bản gộp cả bộ" (Muse hay đăng 1 video
/// chứa 24 tập, vd "[Bản Lồng Tiếng] One Punch Man - Tập 01-24"), và ingest cố ý
/// giữ entry đó ở cuối danh sách để người dùng vẫn xem được bản gộp.
///
/// Vì vậy KHÔNG được đếm thẳng `episodes.length`: bộ 12 tập sẽ hiện
/// "Tập phim (13)" và "1 tập xem được" — sai ngay con số người dùng nhìn thấy.
library;

/// Số tập thật — bỏ entry 0 (bản gộp cả bộ).
int realEpisodeCount(Iterable<int> numbers) => numbers.where((n) => n > 0).length;

/// Tiêu đề danh sách tập. Bộ chỉ có bản gộp thì không được ghi "Tập phim (0)".
String episodesHeaderLabel(int realCount) =>
    realCount > 0 ? 'Tập phim ($realCount)' : 'Bản gộp cả bộ';

/// Nhãn phụ cạnh tiêu đề: chỉ đếm tập thật xem được.
String watchableSuffix(int playableReal, {bool hasBulk = false}) {
  if (playableReal > 0) return '· $playableReal tập xem được';
  if (hasBulk) return '· xem được cả bộ';
  return '· chưa có bản phát miễn phí';
}
