import 'package:cloud_firestore/cloud_firestore.dart';

import '../models/session_data.dart';

class SessionRepository {
  SessionRepository({FirebaseFirestore? firestore})
    : _firestore = firestore ?? FirebaseFirestore.instance;

  final FirebaseFirestore _firestore;

  Stream<SessionData?> watchSession(String sessionId) {
    return _firestore.collection('sessions').doc(sessionId).snapshots().map((
      doc,
    ) {
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

  Stream<List<SessionData>> watchVisibleSessions({int limit = 500}) {
    // Filter + order server-side so we don't read (and pay for) hidden docs.
    // Needs the sessions composite index in firebase/firestore.indexes.json.
    return _firestore
        .collection('sessions')
        .where('status', isEqualTo: 'published')
        .where('visibleInLibrary', isEqualTo: true)
        .orderBy('createdAt', descending: true)
        .limit(limit)
        .snapshots()
        .map((snapshot) {
          // Keep the `test` origin/tag exclusion client-side (not indexed).
          return snapshot.docs
              .map(SessionData.fromDoc)
              .where((session) => session.isPublicInLibrary)
              .toList();
        });
  }

  Stream<List<SessionData>> watchAllSessions({int limit = 300}) {
    return _firestore.collection('sessions').limit(limit).snapshots().map((
      snapshot,
    ) {
      final sessions = snapshot.docs.map(SessionData.fromDoc).toList();
      sessions.sort((a, b) => b.createdAt.compareTo(a.createdAt));
      return sessions;
    });
  }
}
