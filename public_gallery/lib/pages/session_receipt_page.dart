import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class SessionReceiptPage extends StatelessWidget {
  final String sessionId;

  const SessionReceiptPage({super.key, required this.sessionId});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: const Color(0xFF1A1A1A),
        foregroundColor: const Color(0xFFC9A84C),
        title: const Text('Session Receipt'),
        centerTitle: true,
      ),
      body: FutureBuilder<DocumentSnapshot>(
        future: SessionRepository().getSession(sessionId),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError || !snapshot.exists) {
            return Center(child: Text('Session not found'));
          }
          final data = snapshot.data!.data()!;
          final session = SessionData.fromDocument(snapshot.data!);

          return ListView(
            padding: const EdgeInsets.all(20),
            children: [
              SvgPicture.network(
                session.svgUrl ?? '',
                fit: BoxFit.contain,
                placeholder: (context, url) => Center(child: CircularProgressIndicator()),
              ),
              const SizedBox(height: 20),
              Text(
                'Mark: \${session.markName ?? "Unknown"}',
                style: GoogleFonts.cinzel(
                  color: const Color(0xFFC9A84C),
                  fontSize: 24,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                'Oracle Text:',
                style: GoogleFonts.ebGaramond(
                  color: const Color(0xFFCCC5B8),
                  fontSize: 16,
                ),
              ),
              const SizedBox(height: 5),
              Text(
                session.oracleText ?? 'No oracle text available',
                style: GoogleFonts.ebGaramond(
                  color: const Color(0xFFCCC5B8),
                  fontSize: 14,
                ),
              ),
              const SizedBox(height: 20),
              Text(
                'Measurements:',
                style: GoogleFonts.ebGaramond(
                  color: const Color(0xFFCCC5B8),
                  fontSize: 16,
                ),
              ),
              ...session.measures!.map((measure) => ListTile(
                leading: Text(
                  measure['label'] ?? '',
                  style: GoogleFonts.ebGaramond(color: const Color(0xFFCCC5B8)),
                ),
                trailing: Text(
                  measure['value'] ?? '',
                  style: GoogleFonts.ebGaramond(color: const Color(0xFFC9A84C)),
                ),
              )),
              const SizedBox(height: 20),
              Text(
                'Themes:',
                style: GoogleFonts.ebGaramond(
                  color: const Color(0xFFCCC5B8),
                  fontSize: 16,
                ),
              ),
              Wrap(
                spacing: 8,
                children: session.themes!
                    .map((theme) => Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                          decoration: BoxDecoration(
                            color: const Color(0xFFCCC5B8),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Text(
                            theme,
                            style: GoogleFonts.ebGaramond(
                              color: const Color(0xFF1A1A1A),
                              fontSize: 12,
                            ),
                          ),
                        ))
                    .toList(),
              ),
              const SizedBox(height: 20),
              Text(
                'Print Status:',
                style: GoogleFonts.ebGaramond(
                  color: const Color(0xFFCCC5B8),
                  fontSize: 16,
                ),
              ),
              Text(
                session.plotStatus ?? 'Unknown',
                style: GoogleFonts.ebGaramond(
                  color: const Color(0xFFC9A84C),
                  fontSize: 14,
                ),
              ),
              const SizedBox(height: 30),
              ElevatedButton(
                onPressed: () {
                  // Navigate to cloth page with session highlight
                  Navigator.pushNamed(context, '/cloth', arguments: {'session': session.sessionId});
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFFC9A84C),
                  foregroundColor: const Color(0xFF1A1A1A),
                  padding: EdgeInsets.symmetric(horizontal: 30, vertical: 15),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8.0),
                  ),
                ),
                child: const Text(
                  'View in the Cloth',
                  style: TextStyle(
                    color: const Color(0xFF1A1A1A),
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
