import 'package:flutter_test/flutter_test.dart';

import 'package:anistream/core/models/episode_title.dart';

void main() {
  test('bỏ tên placeholder của TMDB', () {
    // 429/526 tên tập trên DB thật là dạng này
    expect(displayEpisodeTitle('Episode 7', 7), isNull);
    expect(displayEpisodeTitle('Ep. 7', 7), isNull);
    expect(displayEpisodeTitle('Tập 7', 7), isNull);
    expect(displayEpisodeTitle('第7話', 7), isNull);
    expect(displayEpisodeTitle('7', 7), isNull);
    expect(displayEpisodeTitle('  EP12 ', 12), isNull);
  });

  test('giữ tên tập thật', () {
    expect(displayEpisodeTitle('Nishikata và cơn mưa', 7), 'Nishikata và cơn mưa');
    expect(displayEpisodeTitle('Episode of the Town', 3), 'Episode of the Town');
  });

  test('rỗng thì không hiện', () {
    expect(displayEpisodeTitle('', 1), isNull);
    expect(displayEpisodeTitle('   ', 1), isNull);
  });
}
