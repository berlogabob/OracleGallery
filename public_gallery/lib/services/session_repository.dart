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
        .where('status', isEqualTo: 'published')
        .orderBy('createdAt', descending: true)
        .limit(limit)
        .snapshots()
        .map((snapshot) {
      return snapshot.docs
          .map(SessionData.fromDoc)
          .where((session) => session.isPublicInLibrary)
          .toList(growable: false);
    });
  }
}
