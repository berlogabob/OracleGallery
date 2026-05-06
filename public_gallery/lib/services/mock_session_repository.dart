import 'dart:async';
import 'package:cloud_firestore/cloud_firestore.dart';

class MockSessionRepository {
  final List<Map<String, dynamic>> _mockSessions = [
    {
      'sessionId': 'test123',
      'sessionUrl': 'https://example.com/#/session/test123',
      'qrUrl': 'https://example.com/#/session/test123',
      'qrImageUrl': 'https://example.com/qr/test123.png',
      'assetUrls': {'qr': 'https://example.com/qr/test123.png'},
      'assetPaths': {'qr': 'sessions/test123/qr.png'},
      'svgUrl': 'https://example.com/sessions/test123/receipt.svg',
      'receiptUrl': 'https://example.com/sessions/test123/receipt.pdf',
      'status': 'published',
      'plotStatus': 'completed',
      'markName': 'The Hero',
      'oracleText': 'This is a sample oracle text.',
      'themes': ['Nature', 'Abstract'],
      'measures': [
        {'label': 'Width', 'value': '100mm'},
        {'label': 'Height', 'value': '100mm'},
      ],
      'origin': 'user',
      'tags': ['test'],
      'visibleInLibrary': true,
    },
  ];

  Stream<DocumentSnapshot> getSessionStream(String sessionId) async* {
    await Future.delayed(Duration(seconds: 1));
    final session = _mockSessions.firstWhere((s) => s['sessionId'] == sessionId, orElse: () => null);
    if (session != null) {
      yield DocumentSnapshot(
        sessionId,
        reference: null,
        data: () => session,
        error: null,
      );
    } else {
      yield DocumentSnapshot(
        sessionId,
        reference: null,
        error: Exception('Session not found'),
      );
    }
  }

  Future<DocumentSnapshot> getSession(String sessionId) async {
    await Future.delayed(Duration(seconds: 1));
    final session = _mockSessions.firstWhere((s) => s['sessionId'] == sessionId, orElse: () => null);
    if (session != null) {
      return DocumentSnapshot(
        sessionId,
        reference: null,
        data: () => session,
        error: null,
      );
    } else {
      return DocumentSnapshot(
        sessionId,
        reference: null,
        error: Exception('Session not found'),
      );
    }
  }

  Stream<QuerySnapshot> getVisibleSessionsStream() async* {
    await Future.delayed(Duration(seconds: 1));
    yield QuerySnapshot(
      documents: _mockSessions.map((session) => DocumentSnapshot(
        session['sessionId'],
        reference: null,
        data: () => session,
        error: null,
      )).toList(),
      error: null,
    );
  }
}
