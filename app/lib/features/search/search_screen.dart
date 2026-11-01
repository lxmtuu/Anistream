import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme.dart';
import '../../core/models/anime.dart';
import '../../core/widgets/net_image.dart';
import '../../data/anime_repository.dart';

class SearchScreen extends ConsumerStatefulWidget {
  const SearchScreen({super.key});

  @override
  ConsumerState<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends ConsumerState<SearchScreen> {
  final _controller = TextEditingController();
  Timer? _debounce;
  List<Anime> _results = const [];
  bool _loading = false;
  String _query = '';
  String? _error;

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () => _run(value));
  }

  Future<void> _run(String value) async {
    final q = value.trim();
    if (q.isEmpty) {
      setState(() {
        _results = const [];
        _query = '';
        _error = null;
        _loading = false;
      });
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final items = await ref.read(animeRepositoryProvider).search(q);
      // Người dùng đã gõ tiếp trong lúc chờ → bỏ kết quả cũ để không "nhảy".
      if (!mounted || q != _controller.text.trim()) return;
      setState(() {
        _results = items;
        _query = q;
        _loading = false;
      });
    } catch (e) {
      // Mất mạng / backend lỗi: hiện lỗi + nút thử lại thay vì treo spinner
      // (trước đây lỗi này làm Future ném ra ngoài và màn hình quay mãi).
      if (!mounted) return;
      setState(() {
        _results = const [];
        _query = q;
        _error = '$e';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final feed = ref.watch(homeFeedProvider);
    final suggestions = feed.maybeWhen(
      data: (d) => d.shelves.isNotEmpty
          ? d.itemsOf(d.shelves.first).take(6).toList()
          : <Anime>[],
      orElse: () => <Anime>[],
    );

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
              child: TextField(
                controller: _controller,
                onChanged: _onChanged,
                autofocus: false,
                textInputAction: TextInputAction.search,
                style: const TextStyle(fontSize: 14),
                decoration: InputDecoration(
                  hintText: 'Tìm anime, romaji hoặc tên gốc…',
                  hintStyle:
                      const TextStyle(color: AppTheme.muted, fontSize: 13),
                  prefixIcon: const Icon(Icons.search_rounded,
                      color: AppTheme.muted, size: 20),
                  suffixIcon: _controller.text.isEmpty
                      ? null
                      : IconButton(
                          icon: const Icon(Icons.close_rounded, size: 18),
                          onPressed: () {
                            _controller.clear();
                            _run('');
                          },
                        ),
                  filled: true,
                  fillColor: AppTheme.surface,
                  contentPadding: const EdgeInsets.symmetric(vertical: 12),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                    borderSide: const BorderSide(color: AppTheme.line),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                    borderSide: const BorderSide(color: AppTheme.line),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                    borderSide: const BorderSide(color: AppTheme.accent),
                  ),
                ),
              ),
            ),
            Expanded(
              child: _loading
                  ? const Center(
                      child:
                          CircularProgressIndicator(color: AppTheme.accent))
                  : _error != null
                      ? _SearchError(
                          message: _error!,
                          onRetry: () => _run(_controller.text),
                        )
                      : _query.isEmpty
                      ? _Suggestions(items: suggestions)
                      : _results.isEmpty
                          ? const Center(
                              child: Text(
                                'Không tìm thấy. Thử tên romaji (vd "frieren").',
                                style: TextStyle(
                                    color: AppTheme.muted, fontSize: 12.5),
                              ),
                            )
                          : ListView.separated(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 16, vertical: 8),
                              itemCount: _results.length,
                              separatorBuilder: (_, __) =>
                                  const Divider(color: AppTheme.line, height: 1),
                              itemBuilder: (context, i) =>
                                  _ResultRow(anime: _results[i]),
                            ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SearchError extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _SearchError({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off_rounded, size: 38, color: AppTheme.muted),
            const SizedBox(height: 12),
            const Text(
              'Không tìm được — kiểm tra kết nối mạng.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 4),
            Text(
              message,
              textAlign: TextAlign.center,
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 10.5, color: AppTheme.muted),
            ),
            const SizedBox(height: 14),
            OutlinedButton(
              onPressed: onRetry,
              style: OutlinedButton.styleFrom(
                foregroundColor: AppTheme.text,
                side: const BorderSide(color: AppTheme.line),
              ),
              child: const Text('Thử lại'),
            ),
          ],
        ),
      ),
    );
  }
}

class _Suggestions extends StatelessWidget {
  final List<Anime> items;
  const _Suggestions({required this.items});

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const Center(
        child: Text('Gõ để tìm kiếm',
            style: TextStyle(color: AppTheme.muted, fontSize: 12.5)),
      );
    }
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        const Text('Gợi ý hôm nay',
            style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700)),
        const SizedBox(height: 10),
        ...items.map((a) => _ResultRow(anime: a)),
      ],
    );
  }
}

class _ResultRow extends StatelessWidget {
  final Anime anime;
  const _ResultRow({required this.anime});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () => context.push('/anime/${anime.slug}'),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 9),
        child: Row(
          children: [
            NetImage(
              url: anime.cover,
              width: 46,
              height: 66,
              radius: BorderRadius.circular(7),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    anime.displayTitle,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 13, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    [
                      if (anime.year != null) '${anime.year}',
                      if (anime.format != null) anime.format!,
                      if (anime.score != null) '★ ${anime.score!.toStringAsFixed(1)}',
                      if (anime.isFree) 'Miễn phí',
                    ].join(' · '),
                    style:
                        const TextStyle(fontSize: 11, color: AppTheme.muted),
                  ),
                ],
              ),
            ),
            const Icon(Icons.chevron_right_rounded, color: AppTheme.muted),
          ],
        ),
      ),
    );
  }
}
