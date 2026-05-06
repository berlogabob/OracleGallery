import 'package:cloud_firestore/cloud_firestore.dart';

import '../models/session_data.dart';

class SessionRepository {
  SessionRepository({FirebaseFirestore? firestore})
      : _firestore = firestore ?? FirebaseFirestore.instance;

  final FirebaseFirestore _firestore;

  Stream<SessionData?> watchSession(String sessionId) {
    return _firestore.collection('sessions').doc(sessionId).snapshots().map((doc) {
      if (!doc.exists) {
        return null;
      }
      return SessionData.fromDoc(doc);
    });
  }

  Future<SessionData?> fetchSession(String sessionId) async {
    final doc = await _firestore.collection('sessions').doc(sessionId).get();
    if (!doc.exists) {
      return null;
    }
    return SessionData.fromDoc(doc);
  }

  Stream<List<SessionData>> watchVisibleSessions({int limit = 150}) {
    return _firestore
        .collection('sessions')
        .limit(limit)
        .snapshots()
        .map((snapshot) {
      final sessions = snapshot.docs
          .map(SessionData.fromDoc)
          .where((session) => session.isPublished && session.isPublicInLibrary)
          .toList();
      sessions.sort((a, b) => b.createdAt.compareTo(a.createdAt));
      return sessions;
    });
  }

  Stream<List<SessionData>> watchAllSessions({int limit = 300}) {
    return _firestore
        .collection('sessions')
        .limit(limit)
        .snapshots()
        .map((snapshot) {
      final sessions = snapshot.docs.map(SessionData.fromDoc).toList();
      sessions.sort((a, b) => b.createdAt.compareTo(a.createdAt));
      return sessions;
    });
  }
}
