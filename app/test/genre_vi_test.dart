import 'package:flutter_test/flutter_test.dart';

import 'package:anistream/core/models/genre_vi.dart';

void main() {
  test('dịch thể loại AniList sang tiếng Việt', () {
    expect(genreVi('Comedy'), 'Hài');
    expect(genreVi('Romance'), 'Lãng mạn');
    expect(genreVi('Slice of Life'), 'Đời thường');
    expect(genreVi('Sci-Fi'), 'Khoa học viễn tưởng');
  });

  test('thể loại lạ giữ nguyên, không trả rỗng', () {
    expect(genreVi('Gourmet'), 'Ẩm thực');
    expect(genreVi('Some New Genre'), 'Some New Genre');
    expect(genreVi('  Comedy  '), 'Hài');
  });
}
