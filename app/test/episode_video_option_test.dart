import 'package:flutter_test/flutter_test.dart';

import '../lib/core/models/anime.dart';

void main() {
  test('Episode parses every official video option', () {
    final episode = Episode.fromJson({
      'number': 92,
      'title': '',
      'video_id': 'CZpSrs9vdII',
      'platform': 'youtube',
      'airing_at': null,
      'video_options': [
        {
          'video_id': 'CZpSrs9vdII',
          'platform': 'youtube',
          'label': 'Vietsub',
        },
        {
          'video_id': 'IS4klIOOrC8',
          'platform': 'youtube',
          'label': 'Lồng tiếng',
        },
      ],
    });

    expect(episode.playable, isTrue);
    expect(episode.videoOptions, hasLength(2));
    expect(episode.videoOptions.map((option) => option.videoId), [
      'CZpSrs9vdII',
      'IS4klIOOrC8',
    ]);
    expect(episode.videoOptions.map((option) => option.label), [
      'Vietsub',
      'Lồng tiếng',
    ]);
  });

  test('Episode remains compatible with older API payloads', () {
    final episode = Episode.fromJson({
      'number': 1,
      'title': '',
      'video_id': 'abcdefghijk',
      'platform': 'youtube',
      'airing_at': null,
    });

    expect(episode.playable, isTrue);
    expect(episode.videoOptions, isEmpty);
  });
}
