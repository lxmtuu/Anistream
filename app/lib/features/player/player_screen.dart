import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:youtube_player_iframe/youtube_player_iframe.dart';

import '../../app/theme.dart';

/// Phát video official bằng **IFrame Player API chính thức của YouTube**.
///
/// Vì sao làm thế này:
///  • Hợp pháp: dùng đúng player chính thức, không trích xuất luồng video,
///    không chặn quảng cáo của chủ kênh.
///  • 0đ: YouTube chịu toàn bộ băng thông.
///  • Tự động tuân thủ điều kiện "cho nhúng" của video (đã lọc bằng oEmbed ở ingest).
///
/// Desktop (Windows/macOS/Linux): webview chưa hỗ trợ tốt → mở bằng app YouTube
/// hoặc trình duyệt (vẫn là trải nghiệm hợp pháp, không cần host gì).
class PlayerScreen extends StatefulWidget {
  final String videoId;
  final String title;

  const PlayerScreen({super.key, required this.videoId, required this.title});

  @override
  State<PlayerScreen> createState() => _PlayerScreenState();
}

class _PlayerScreenState extends State<PlayerScreen> {
  YoutubePlayerController? _controller;

  static bool get _canEmbed {
    if (kIsWeb) return true;
    return defaultTargetPlatform == TargetPlatform.android ||
        defaultTargetPlatform == TargetPlatform.iOS;
  }

  @override
  void initState() {
    super.initState();
    if (_canEmbed) {
      _controller = YoutubePlayerController.fromVideoId(
        videoId: widget.videoId,
        autoPlay: true,
        // Chỉ truyền tham số cơ bản nhất để không phụ thuộc phiên bản plugin.
        // Muốn chỉnh thêm: xem `YoutubePlayerParams` trong tài liệu package.
        params: const YoutubePlayerParams(
          showFullscreenButton: true,
        ),
      );
    }
  }

  @override
  void dispose() {
    _controller?.close();
    super.dispose();
  }

  Future<void> _openExternal() async {
    final uri =
        Uri.parse('https://www.youtube.com/watch?v=${widget.videoId}');
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        leading: IconButton(
          icon: const Icon(Icons.close_rounded),
          onPressed: () => context.pop(),
        ),
        title: Text(
          widget.title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
        ),
      ),
      body: controller != null
          ? Column(
              children: [
                AspectRatio(
                  aspectRatio: 16 / 9,
                  child: YoutubePlayer(controller: controller),
                ),
                const Padding(
                  padding: EdgeInsets.all(16),
                  child: Row(
                    children: [
                      Icon(Icons.verified_outlined,
                          size: 15, color: AppTheme.green),
                      SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Video official của chủ kênh, phát qua trình phát '
                          'YouTube chính thức. AniStream không lưu trữ video.',
                          style: TextStyle(
                            fontSize: 11,
                            height: 1.5,
                            color: AppTheme.muted,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            )
          : Center(
              child: Padding(
                padding: const EdgeInsets.all(28),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(Icons.desktop_windows_outlined,
                        size: 40, color: AppTheme.muted),
                    const SizedBox(height: 14),
                    const Text(
                      'Bản desktop chưa nhúng player',
                      style: TextStyle(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      'Mở video official bằng trình duyệt. (v1.1 sẽ tích hợp\n'
                      'webview trên Windows/macOS.)',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                          fontSize: 11.5, color: AppTheme.muted, height: 1.5),
                    ),
                    const SizedBox(height: 18),
                    FilledButton.icon(
                      onPressed: _openExternal,
                      icon: const Icon(Icons.open_in_new_rounded, size: 18),
                      label: const Text('Mở video official'),
                    ),
                  ],
                ),
              ),
            ),
    );
  }
}
