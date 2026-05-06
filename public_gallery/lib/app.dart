import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'pages/about_page.dart';
import 'pages/cloth_page.dart';
import 'pages/home_page.dart';
import 'pages/marks_page.dart';
import 'pages/session_receipt_page.dart';
import 'theme/oracle_theme.dart';
import 'widgets/oracle_shell.dart';

class OracleGalleryApp extends StatelessWidget {
  const OracleGalleryApp({super.key, required this.firebaseReady});

  final bool firebaseReady;

  @override
  Widget build(BuildContext context) {
    final router = GoRouter(
      routes: [
        ShellRoute(
          builder: (context, state, child) => OracleShell(
            currentPath: state.uri.path,
            child: child,
          ),
          routes: [
            GoRoute(path: '/', builder: (context, state) => const HomePage()),
            GoRoute(
              path: '/cloth',
              builder: (context, state) => ClothPage(
                firebaseReady: firebaseReady,
                highlightSessionId: state.uri.queryParameters['session'],
              ),
            ),
            GoRoute(path: '/library', redirect: (context, state) => '/cloth'),
            GoRoute(path: '/marks', builder: (context, state) => const MarksPage()),
            GoRoute(path: '/about', builder: (context, state) => const AboutPage()),
            GoRoute(
              path: '/session/:sessionId',
              builder: (context, state) => SessionReceiptPage(
                firebaseReady: firebaseReady,
                sessionId: state.pathParameters['sessionId'] ?? '',
              ),
            ),
          ],
        ),
      ],
    );

    return MaterialApp.router(
      title: 'Oracle Gallery',
      debugShowCheckedModeBanner: false,
      theme: OracleTheme.light(),
      routerConfig: router,
    );
  }
}
