import 'package:flutter_test/flutter_test.dart';

import 'package:anistream/core/models/episode_count.dart';

void main() {
  test('không đếm bản gộp cả bộ (number = 0)', () {
    // Ca thật: bộ 12 tập + 1 link "Tập 01-12" → API trả 13 entry.
    expect(realEpisodeCount([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 0]), 12);
    expect(episodesHeaderLabel(12), 'Tập phim (12)');
  });

  test('bộ chỉ có bản gộp thì không hiện "Tập phim (0)"', () {
    expect(realEpisodeCount([0]), 0);
    expect(episodesHeaderLabel(0), 'Bản gộp cả bộ');
  });

  test('nhãn xem được chỉ tính tập thật', () {
    expect(watchableSuffix(5), '· 5 tập xem được');
    expect(watchableSuffix(0, hasBulk: true), '· xem được cả bộ');
    expect(watchableSuffix(0), '· chưa có bản phát miễn phí');
  });
}
