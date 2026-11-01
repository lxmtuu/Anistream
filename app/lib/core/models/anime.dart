// Model dữ liệu. Không dùng freezed/build_runner ở v1 để bạn `flutter pub get`
// là chạy được ngay, không cần chạy codegen.

class Episode {
  final int number;
  final String title;
  final String? videoId; // != null → phát được trong app (video official, cho nhúng)
  final String? platform;
  final DateTime? airingAt;

  const Episode({
    required this.number,
    required this.title,
    this.videoId,
    this.platform,
    this.airingAt,
  });

  bool get playable => videoId != null && videoId!.isNotEmpty;

  factory Episode.fromJson(Map<String, dynamic> j) => Episode(
        number: (j['number'] as num?)?.toInt() ?? 0,
        title: (j['title'] as String?) ?? '',
        videoId: j['video_id'] as String?,
        platform: j['platform'] as String?,
        airingAt: DateTime.tryParse((j['airing_at'] as String?) ?? '')?.toLocal(),
      );
}

class PlatformLink {
  final String name;
  final String url;
  final bool verified;

  const PlatformLink({
    required this.name,
    required this.url,
    this.verified = false,
  });

  factory PlatformLink.fromJson(Map<String, dynamic> j) => PlatformLink(
        name: (j['name'] as String?) ?? '',
        url: (j['url'] as String?) ?? '',
        verified: (j['verified'] as bool?) ?? false,
      );
}

class Anime {
  final int id;
  final String slug;
  final String title;
  final String? titleVi;
  final String? titleNative;
  final String? cover;
  final String? banner;
  final double? score;
  final int? year;
  final String? season;
  final String? format;
  final String? status;
  final int? episodesTotal;
  final List<String> genres;
  final String synopsis;
  final bool isFree;
  final List<PlatformLink> platforms;
  final List<Episode> episodes;
  final int popularity;

  const Anime({
    required this.id,
    required this.slug,
    required this.title,
    this.titleVi,
    this.titleNative,
    this.cover,
    this.banner,
    this.score,
    this.year,
    this.season,
    this.format,
    this.status,
    this.episodesTotal,
    this.genres = const [],
    this.synopsis = '',
    this.isFree = false,
    this.platforms = const [],
    this.episodes = const [],
    this.popularity = 0,
  });

  /// Ưu tiên tên tiếng Việt (từ TMDB) → romaji → english
  String get displayTitle =>
      (titleVi != null && titleVi!.isNotEmpty) ? titleVi! : title;

  /// Tập phát được trong app đầu tiên (để bấm "Xem ngay")
  Episode? get firstPlayable {
    for (final e in episodes) {
      if (e.playable) return e;
    }
    return null;
  }

  Episode? get nextEpisode {
    final future = episodes.where((e) => e.airingAt != null).toList()
      ..sort((a, b) => a.airingAt!.compareTo(b.airingAt!));
    for (final e in future) {
      if (e.airingAt!.isAfter(DateTime.now())) return e;
    }
    return episodes.isEmpty ? null : episodes.last;
  }

  factory Anime.fromJson(Map<String, dynamic> j) => Anime(
        id: (j['id'] as num).toInt(),
        slug: (j['slug'] as String?) ?? '',
        title: (j['title'] as String?) ?? '',
        titleVi: j['title_vi'] as String?,
        titleNative: j['title_native'] as String?,
        cover: j['cover'] as String?,
        banner: j['banner'] as String?,
        score: (j['score'] as num?)?.toDouble(),
        year: (j['year'] as num?)?.toInt(),
        season: j['season'] as String?,
        format: j['format'] as String?,
        status: j['status'] as String?,
        episodesTotal: (j['episodes_total'] as num?)?.toInt(),
        genres: ((j['genres'] as List?) ?? const [])
            .map((e) => e.toString())
            .toList(),
        synopsis: (j['synopsis'] as String?) ?? '',
        isFree: (j['is_free'] as bool?) ?? false,
        platforms: ((j['platforms'] as List?) ?? const [])
            .map((e) => PlatformLink.fromJson(e as Map<String, dynamic>))
            .toList(),
        episodes: ((j['episodes'] as List?) ?? const [])
            .map((e) => Episode.fromJson(e as Map<String, dynamic>))
            .toList(),
        popularity: (j['popularity'] as num?)?.toInt() ?? 0,
      );
}

class Shelf {
  final String title;
  final String kind;
  final List<int> ids;

  const Shelf({required this.title, required this.kind, required this.ids});

  factory Shelf.fromJson(Map<String, dynamic> j) => Shelf(
        title: (j['title'] as String?) ?? '',
        kind: (j['kind'] as String?) ?? '',
        ids: ((j['ids'] as List?) ?? const [])
            .map((e) => (e as num).toInt())
            .toList(),
      );
}

class ScheduleSlot {
  final int animeId;
  final int episode;
  final DateTime airingAt;

  const ScheduleSlot({
    required this.animeId,
    required this.episode,
    required this.airingAt,
  });

  factory ScheduleSlot.fromJson(Map<String, dynamic> j) => ScheduleSlot(
        animeId: (j['anime_id'] as num).toInt(),
        episode: (j['episode'] as num?)?.toInt() ?? 0,
        airingAt: DateTime.parse(j['airing_at'] as String).toLocal(),
      );
}
