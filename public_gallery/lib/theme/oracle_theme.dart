import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class OracleColors {
  static const cream = Color(0xFFF7F4EF);
  static const paper = Color(0xFFFBF8F1);
  static const ink = Color(0xFF1A1A1A);
  static const inkMid = Color(0xFF3A3A3A);
  static const inkMuted = Color(0xFF6A6A6A);
  static const rust = Color(0xFF8B4513);
  static const gold = Color(0xFFC9A84C);
  static const goldDim = Color(0xFF8A6F2E);
  static const rule = Color(0xFFCCC5B8);
  static const voidColor = Color(0xFF0A0A12);
}

class OracleTheme {
  static ThemeData light() {
    final bodyTheme = GoogleFonts.ebGaramondTextTheme();
    return ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: OracleColors.cream,
      colorScheme: ColorScheme.fromSeed(
        seedColor: OracleColors.rust,
        brightness: Brightness.light,
        primary: OracleColors.ink,
        secondary: OracleColors.rust,
        surface: OracleColors.paper,
        onSurface: OracleColors.ink,
      ),
      textTheme: bodyTheme.copyWith(
        displayLarge: GoogleFonts.cinzelDecorative(
          fontSize: 44,
          letterSpacing: 7,
          color: OracleColors.ink,
          fontWeight: FontWeight.w400,
        ),
        headlineMedium: GoogleFonts.cinzel(
          fontSize: 20,
          letterSpacing: 4,
          color: OracleColors.ink,
          fontWeight: FontWeight.w400,
        ),
        titleMedium: GoogleFonts.cinzel(
          fontSize: 13,
          letterSpacing: 2.4,
          color: OracleColors.rust,
          fontWeight: FontWeight.w600,
        ),
        bodyLarge: GoogleFonts.ebGaramond(
          fontSize: 18,
          height: 1.55,
          color: OracleColors.inkMid,
        ),
        bodyMedium: GoogleFonts.ebGaramond(
          fontSize: 15,
          height: 1.45,
          color: OracleColors.inkMuted,
        ),
      ),
    );
  }
}
