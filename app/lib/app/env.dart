/// Cấu hình build-time. Không hardcode secret trong app.
///
/// Chạy với backend thật:
///   flutter run --dart-define=USE_MOCK=false \
///               --dart-define=API_BASE=https://<project>.supabase.co/functions/v1
///
/// Chạy với dữ liệu mẫu (mặc định, không cần backend):
///   flutter run
class Env {
  static const bool useMock =
      bool.fromEnvironment('USE_MOCK', defaultValue: true);

  static const String apiBase =
      String.fromEnvironment('API_BASE', defaultValue: '');

  /// anon key — ĐƯỢC PHÉP nằm trong app (RLS bảo vệ), KHÔNG BAO GIỜ dùng service_role
  static const String anonKey =
      String.fromEnvironment('ANON_KEY', defaultValue: '');

  static bool get hasBackend => !useMock && apiBase.isNotEmpty;

  /// Gốc PostgREST, suy ra từ API_BASE.
  /// vd API_BASE = https://abc.supabase.co/functions/v1 → restBase = https://abc.supabase.co
  /// Dùng để app tự ghi `push_subscriptions` (RLS cho phép với user_id null).
  static String get restBase {
    if (apiBase.isEmpty) return '';
    final i = apiBase.indexOf('/functions/');
    return i > 0 ? apiBase.substring(0, i) : apiBase;
  }
}
