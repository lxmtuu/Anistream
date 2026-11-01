import 'package:flutter/material.dart';

/// Dark-first (app xem phim), 1 accent duy nhất để không loè loẹt.
class AppTheme {
  static const Color bg = Color(0xFF0B0E14);
  static const Color surface = Color(0xFF141926);
  static const Color surface2 = Color(0xFF1B2131);
  static const Color line = Color(0xFF252D40);
  static const Color accent = Color(0xFF7C5CFF);
  static const Color green = Color(0xFF3DDC97);
  static const Color text = Color(0xFFE8ECF4);
  static const Color muted = Color(0xFF8B94A8);

  static ThemeData dark() {
    final base = ThemeData.dark(useMaterial3: true);
    return base.copyWith(
      scaffoldBackgroundColor: bg,
      colorScheme: base.colorScheme.copyWith(
        primary: accent,
        secondary: green,
        surface: surface,
        onSurface: text,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        centerTitle: false,
      ),
      textTheme: base.textTheme.apply(
        bodyColor: text,
        displayColor: text,
      ),
      chipTheme: base.chipTheme.copyWith(
        backgroundColor: surface2,
        side: const BorderSide(color: line),
        labelStyle: const TextStyle(color: text, fontSize: 12),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: surface,
        indicatorColor: accent.withAlpha(56),
        labelTextStyle: WidgetStateProperty.all(
          const TextStyle(fontSize: 11, color: text),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: accent,
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
          textStyle: const TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      snackBarTheme: const SnackBarThemeData(
        backgroundColor: surface2,
        contentTextStyle: TextStyle(color: text),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }
}

/// Định dạng thời gian không cần locale data (tránh initializeDateFormatting)
class VnTime {
  static const _weekdays = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];

  static String hhmm(DateTime t) =>
      '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';

  static String dayLabel(DateTime t) =>
      '${_weekdays[t.weekday - 1]} ${t.day.toString().padLeft(2, '0')}/${t.month.toString().padLeft(2, '0')}';

  /// `countdown` chỉ dành cho mốc SẮP tới. Với mốc đã qua nó trả 'đang chiếu',
  /// nghe như tập chiếu năm 2018 vẫn đang phát → dùng `airStatus` khi chưa chắc.
  static String countdown(DateTime t) {
    final d = t.difference(DateTime.now());
    if (d.isNegative) return 'đã chiếu';
    if (d.inDays >= 1) return '${d.inDays} ngày nữa';
    if (d.inHours >= 1) return '${d.inHours}h${(d.inMinutes % 60).toString().padLeft(2, '0')}p';
    return '${d.inMinutes} phút nữa';
  }

  /// Nhãn trạng thái phát sóng: 'đã chiếu' / '3 ngày nữa' / '2h05p' / '12 phút nữa'.
  static String airStatus(DateTime t) {
    if (!t.isAfter(DateTime.now())) return 'đã chiếu';
    return countdown(t);
  }
}
