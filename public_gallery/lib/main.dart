import 'package:firebase_core/firebase_core.dart';
import 'firebase_config.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:flutter/material.dart';
import 'pages/home_page.dart';
import 'pages/cloth_page.dart';
import 'pages/marks_page.dart';
import 'pages/about_page.dart';
import 'pages/session_receipt_page.dart';

import 'theme/oracle_theme.dart';
import 'widgets/oracle_shell.dart';
import 'services/session_repository.dart';
import 'global_router_delegate.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  setUrlStrategy(HashUrlStrategy());
  final firebaseOptions = await GalleryFirebaseConfig.load();
  if (firebaseOptions != null) {
    await Firebase.initializeApp(options: firebaseOptions);
  }
  runApp(OracleGalleryApp(firebaseReady: firebaseOptions != null));
}

class OracleGalleryApp extends StatelessWidget {
  final bool firebaseReady;

  const OracleGalleryApp({super.key, required this.firebaseReady});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Oracle Gallery',
      debugShowCheckedModeBanner: false,
      theme: _themeData,
      darkTheme: _darkThemeData,
      themeMode: ThemeMode.system,
      builder: (context, child) => OracleShell(child: child!),
      routeInformationParser: GoRouter().routeInformationParser,
      routeInformationProvider: GoRouter().routeInformationProvider,
      routerDelegate: GlobalRouterDelegate(context, firebaseReady: firebaseReady, firebaseFirestore: firebaseReady ? FirebaseFirestore.instance : null),
      backButtonDispatcher: GoRouter().backButtonDispatcher,
    );
  }

  static final ThemeData _themeData = ThemeData(
    useMaterial3: true,
    fontFamily: GoogleFonts.era().fontFamily,
    textTheme: GoogleFonts.eraTextTheme(),
    colorScheme: ColorScheme(
      primary: _charcoal,
      secondary: Color(0xFFC9A84C),
      background: _cream,
      surface: _paper,
      error: Colors.red,
      onPrimary: _paper,
      onSecondary: _charcoal,
      onBackground: _charcoal,
      onSurface: _charcoal,
    ),
  );

  static final ThemeData _darkThemeData = ThemeData(
    useMaterial3: true,
    fontFamily: GoogleFonts.eraTextTheme(),
    textTheme: GoogleFonts.eraTextTheme(),
    colorScheme: ColorScheme(
      primary: Color(0xFF1A1A1A),
      secondary: Color(0xFFC9A84C),
      background: Color(0xFF1A1A1A),
      surface: Color(0xFF1A1A1A),
      error: Colors.red,
      onPrimary: Color(0xFF1A1A1A),
      onSecondary: Color(0xFF1A1A1A),
      onBackground: Color(0xFF1A1A1A),
      onSurface: Color(0xFF1A1A1A),
    ),
  );
}
