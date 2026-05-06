import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme/oracle_theme.dart';
import '../widgets/oracle_primitives.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final TextEditingController _sessionController = TextEditingController();

  @override
  void dispose() {
    _sessionController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return OraclePage(
      children: [
        Container(
          color: OracleColors.voidColor,
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 72),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 940),
              child: Column(
                children: [
                  Text(
                    'THE ORACLE',
                    textAlign: TextAlign.center,
                    style: GoogleFonts.cinzelDecorative(
                      color: OracleColors.gold,
                      fontSize: 42,
                      letterSpacing: 8,
                    ),
                  ),
                  const SizedBox(height: 18),
                  Text(
                    'A public cloth of generated marks, receipts, and printed fragments.',
                    textAlign: TextAlign.center,
                    style: GoogleFonts.ebGaramond(
                      color: OracleColors.cream,
                      fontSize: 22,
                      fontStyle: FontStyle.italic,
                      height: 1.35,
                    ),
                  ),
                  const SizedBox(height: 34),
                  Wrap(
                    alignment: WrapAlignment.center,
                    spacing: 14,
                    runSpacing: 14,
                    children: [
                      FilledButton(
                        onPressed: () => context.go('/cloth'),
                        child: const Text('Enter the cloth'),
                      ),
                      OutlinedButton(
                        onPressed: () => context.go('/marks'),
                        child: const Text('The marks'),
                      ),
                      OutlinedButton(
                        onPressed: () => context.go('/about'),
                        child: const Text('About'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
        OracleSection(
          label: 'QR receipt',
          title: 'Open a session directly from a printed receipt.',
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _sessionController,
                  decoration: const InputDecoration(
                    labelText: 'Session ID',
                    hintText: '20260428_183129',
                  ),
                  onSubmitted: _openSession,
                ),
              ),
              const SizedBox(width: 12),
              FilledButton(onPressed: () => _openSession(_sessionController.text), child: const Text('Open')),
            ],
          ),
        ),
      ],
    );
  }

  void _openSession(String value) {
    final sessionId = value.trim();
    if (sessionId.isNotEmpty) {
      context.go('/session/$sessionId');
    }
  }
}
