import 'package:firebase_core/firebase_core.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter/material.dart';
import '../services/session_repository.dart';
import '../services/mock_session_repository.dart';

class GlobalRouterDelegate extends GoRouterDelegate {
  final BuildContext context;
  final bool firebaseReady;
  final FirebaseFirestore? firebaseFirestore;

  GlobalRouterDelegate(this.context, {required this.firebaseReady, this.firebaseFirestore})
      : _sessionRepository = firebaseFirestore != null
            ? SessionRepository(firestore: firebaseFirestore)
            : MockSessionRepository();
      : _sessionRepository = firebaseFirestore != null
            ? SessionRepository(firestore: firebaseFirestore)
            : SessionRepository();;

  @override
  Widget build(BuildContext context) {
    return GoRouter(
      routes: _routes,
      initialLocation: _initialRoute,
      redirect: _redirect,
    );
  }

  @override
  GlobalKey<NavigatorState> get navigatorKey => GlobalKey<NavigatorState>();

  static List<RouteData> get _routes => [
        RouteData(path: '/', name: '/', pageBuilder: (_, __, ___) => HomePage()),
        RouteData(path: '/cloth', name: 'cloth', pageBuilder: (_, __, ___) => ClothPage()),
        RouteData(path: '/cloth/:sessionId', name: 'cloth.session', pageBuilder: (_, p) => ClothPage(sessionId: p['sessionId'])),
        RouteData(path: '/marks', name: 'marks', pageBuilder: (_, __, ___) => MarksPage()),
        RouteData(path: '/about', name: 'about', pageBuilder: (_, __, ___) => AboutPage()),
        RouteData(path: '/session/:sessionId', name: 'session', pageBuilder: (_, p) => SessionReceiptPage(sessionId: p['sessionId'])),
      ];

  static String get _initialRoute => '/';

  static RouteData? _redirect(String? path, GoRouterState state) {
    if (path == null) return null;
    if (path == '/library') {
      return state.router.routeData('cloth');
    }
    return null;
  }
}
