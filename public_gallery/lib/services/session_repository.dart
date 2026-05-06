import 'dart:async';
import 'package:cloud_firestore/cloud_firestore.dart';

class SessionRepository {
  final FirebaseFirestore _firestore;

  SessionRepository({FirebaseFirestore? firestore})
      : _firestore = firestore ?? FirebaseFirestore.instance;

  Stream<DocumentSnapshot> getSessionStream(String sessionId) async* {
    yield* _firestore.collection('sessions').doc(sessionId).snapshots();
  }

  Future<DocumentSnapshot> getSession(String sessionId) async {
    try {
      return await _firestore.collection('sessions').doc(sessionId).get();
    } catch (e) {
      return DocumentSnapshot(null, reference: null, error: e);
    }
  }

  Stream<QuerySnapshot> getVisibleSessionsStream() async* {
    yield await _firestore
        .collection('sessions')
        .where('status', isEqualTo: 'published')
        .where('visibleInLibrary', isEqualTo: true)
        .where('origin', isNotEqualTo: 'test')
        .orderBy('created_at', descending)
        .limit(100)
        .snapshots();
  }
}
