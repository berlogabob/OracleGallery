import 'package:flutter/material.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/session_repository.dart';

class ClothPage extends StatelessWidget {
  final String? sessionId;

  const ClothPage({super.key, this.sessionId});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: const Color(0xFF1A1A1A),
        foregroundColor: const Color(0xFFC9A84C),
        title: const Text('The Cloth'),
        centerTitle: true,
      ),
      body: StreamBuilder<DocumentSnapshot>(
        stream: sessionId != null
            ? SessionRepository().getSessionStream(sessionId!)
            : SessionRepository().getVisibleSessionsStream().map((snap) {
                // Преобразуем QuerySnapshot в первый документ для выделения
                if (snap.docs.isNotEmpty) {
                  return snap.docs[0];
                }
                return DocumentSnapshot(null, reference: null, data: () => null, error: null);
              }),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError || !snapshot.exists) {
            return Center(child: Text('Error loading sessions'));
          }
          final data = snapshot.data!.data()!;
          final session = SessionData.fromDocument(snapshot.data!);

          return ListView(
            children: [
              if (sessionId != null)
                _buildSessionCard(session),
              if (sessionId == null)
                _buildSessionList(session),
            ],
          );
        },
      ),
    );
  }

  Widget _buildSessionCard(SessionData session) {
    return Card(
      color: const Color(0xFF1A1A1A),
      child: Column(
        children: [
          SvgPicture.network(session.svgUrl ?? ''),
          Text(
            session.markName ?? '',
            style: GoogleFonts.cinzel(
              color: const Color(0xFFC9A84C),
              fontSize: 24,
            ),
          ),
          Text(
            session.oracleText ?? '',
            style: GoogleFonts.ebGaramond(
              color: const Color(0xFFCCC5B8),
              fontSize: 16,
            ),
          ),
          ElevatedButton(
            onPressed: () {
              // Navigate to session receipt
              Navigator.pushNamed(context, '/session/${session.sessionId}');
            },
            child: const Text('View Receipt'),
          ),
        ],
      ),
    );
  }

  Widget _buildSessionList(QuerySnapshot snapshot) {
    return ListView.builder(
      itemCount: snapshot.docs.length,
      itemBuilder: (context, index) {
        final session = SessionData.fromDocument(snapshot.docs[index]);
        return Card(
          color: const Color(0xFF1A1A1A),
          child: ListTile(
            leading: SvgPicture.network(session.svgUrl ?? ''),
            title: Text(
              session.markName ?? '',
              style: GoogleFonts.cinzel(color: const Color(0xFFC9A84C)),
            ),
            subtitle: Text(
              session.oracleText ?? '',
              style: GoogleFonts.ebGaramond(color: const Color(0xFFCCC5B8)),
            ),
            onTap: () {
              Navigator.pushNamed(context, '/session/${session.sessionId}');
            },
          ),
        );
      },
    );
  }
}
