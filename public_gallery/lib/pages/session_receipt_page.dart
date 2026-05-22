import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../models/session_data.dart';
import '../services/session_repository.dart';
import '../theme/oracle_theme.dart';
import '../widgets/oracle_primitives.dart';

class SessionReceiptPage extends StatelessWidget {
  const SessionReceiptPage({
    super.key,
    required this.firebaseReady,
    required this.sessionId,
  });

  final bool firebaseReady;
  final String sessionId;

  @override
  Widget build(BuildContext context) {
    if (!firebaseReady) {
      return const OraclePage(
        children: [
          OracleSection(
            label: 'Session',
            title: 'Firebase is not configured.',
            child: ConfigHelpCard(),
          ),
        ],
      );
    }

    return StreamBuilder<SessionData?>(
      stream: SessionRepository().watchSession(sessionId),
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return OraclePage(
            children: [
              OracleSection(
                label: 'Session',
                title: 'The receipt could not be loaded.',
                child: StatusPanel(
                  title: 'Firestore error',
                  message: snapshot.error.toString(),
                ),
              ),
            ],
          );
        }
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const OraclePage(
            children: [
              OracleSection(
                label: 'Session',
                title: 'The receipt is opening.',
                child: Center(
                  child: Padding(
                    padding: EdgeInsets.all(28),
                    child: CircularProgressIndicator(),
                  ),
                ),
              ),
            ],
          );
        }

        final session = snapshot.data;
        if (session == null || !session.isPublished) {
          return OraclePage(
            children: [
              OracleSection(
                label: 'Session',
                title: 'This fragment is still publishing.',
                child: StatusPanel(
                  title: sessionId,
                  message:
                      'The QR route is valid, but the uploader has not finished publishing the public receipt yet.',
                ),
              ),
            ],
          );
        }

        return OraclePage(
          children: [
            OracleSection(
              label: 'Digital receipt',
              title: 'This fragment remains.',
              child: _Receipt(session: session),
            ),
          ],
        );
      },
    );
  }
}

class _Receipt extends StatelessWidget {
  const _Receipt({required this.session});

  final SessionData session;

  @override
  Widget build(BuildContext context) {
    final created = session.createdAt.toLocal();
    final dateLine =
        '${created.day.toString().padLeft(2, '0')} · ${created.month.toString().padLeft(2, '0')} · ${created.year} · ${created.hour.toString().padLeft(2, '0')}:${created.minute.toString().padLeft(2, '0')}';

    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 34),
          decoration: BoxDecoration(
            color: OracleColors.paper,
            border: Border.all(color: OracleColors.rule, width: 0.8),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'THE ORACLE',
                textAlign: TextAlign.center,
                style: GoogleFonts.cinzel(
                  color: OracleColors.gold,
                  fontSize: 20,
                  letterSpacing: 5,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                dateLine,
                textAlign: TextAlign.center,
                style: GoogleFonts.cinzel(
                  color: OracleColors.inkMuted,
                  fontSize: 11,
                  letterSpacing: 4,
                ),
              ),
              const SizedBox(height: 34),
              _Rule(label: 'THE MARK'),
              const SizedBox(height: 18),
              if (session.tarotUrl.isNotEmpty) ...[
                _TarotImage(tarotUrl: session.tarotUrl),
                const SizedBox(height: 22),
              ],
              Center(
                child: SymbolNetworkView(svgUrl: session.svgUrl, size: 160),
              ),
              const SizedBox(height: 26),
              Text(
                session.markName.isEmpty
                    ? 'THE UNNAMED MARK'
                    : session.markName.toUpperCase(),
                textAlign: TextAlign.center,
                style: GoogleFonts.cinzel(
                  color: OracleColors.ink,
                  fontSize: 22,
                  letterSpacing: 3,
                ),
              ),
              const SizedBox(height: 28),
              _Rule(label: 'WHAT THE ORACLE PERCEIVED'),
              const SizedBox(height: 14),
              Text(
                session.oracleText.isEmpty
                    ? 'The oracle has not spoken yet.'
                    : session.oracleText,
                textAlign: TextAlign.center,
                style: GoogleFonts.ebGaramond(
                  color: OracleColors.inkMid,
                  fontSize: 18,
                  fontStyle: FontStyle.italic,
                  height: 1.35,
                ),
              ),
              const SizedBox(height: 28),
              _Rule(label: 'WHAT THE SYSTEM MEASURED'),
              const SizedBox(height: 14),
              ..._measureRows(context, session.measures),
              const SizedBox(height: 24),
              _Rule(label: 'THEMES'),
              const SizedBox(height: 14),
              Text(
                session.themes.isEmpty
                    ? 'UNSPECIFIED'
                    : session.themes.map((t) => t.toUpperCase()).join(' · '),
                textAlign: TextAlign.center,
                style: GoogleFonts.cinzel(
                  color: OracleColors.ink,
                  fontSize: 15,
                  letterSpacing: 2.5,
                ),
              ),
              const SizedBox(height: 24),
              Text(
                'PRINT STATUS · ${session.plotStatus.toUpperCase()}',
                textAlign: TextAlign.center,
                style: GoogleFonts.cinzel(
                  color: OracleColors.goldDim,
                  fontSize: 10,
                  letterSpacing: 2.4,
                ),
              ),
              if (session.qrImageUrl.isNotEmpty) ...[
                const SizedBox(height: 22),
                _QrImage(qrImageUrl: session.qrImageUrl),
              ],
              const SizedBox(height: 22),
              OutlinedButton(
                onPressed: () => context.go(
                  '/cloth?session=${Uri.encodeQueryComponent(session.sessionId)}',
                ),
                child: const Text('View in the cloth'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _measureRows(
    BuildContext context,
    Map<String, double> measures,
  ) {
    if (measures.isEmpty) {
      return [
        Text(
          'No measurements published.',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodyMedium,
        ),
      ];
    }
    return measures.entries.map((entry) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(
              width: 150,
              child: Text(
                entry.key.toUpperCase(),
                textAlign: TextAlign.right,
                style: GoogleFonts.cinzel(
                  color: OracleColors.inkMid,
                  fontSize: 12,
                  letterSpacing: 1.6,
                ),
              ),
            ),
            const SizedBox(width: 24),
            SizedBox(
              width: 54,
              child: Text(
                entry.value.toStringAsFixed(2),
                style: GoogleFonts.cinzel(
                  color: OracleColors.ink,
                  fontSize: 12,
                  letterSpacing: 1.6,
                ),
              ),
            ),
          ],
        ),
      );
    }).toList();
  }
}

class _QrImage extends StatelessWidget {
  const _QrImage({required this.qrImageUrl});

  final String qrImageUrl;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: OracleColors.cream,
        border: Border.all(color: OracleColors.rule, width: 0.7),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'QR RECEIPT',
            textAlign: TextAlign.center,
            style: GoogleFonts.cinzel(
              color: OracleColors.rust,
              fontSize: 10,
              letterSpacing: 3,
            ),
          ),
          const SizedBox(height: 14),
          Center(
            child: SizedBox(
              width: 96,
              height: 96,
              child: Image.network(
                qrImageUrl,
                fit: BoxFit.contain,
                errorBuilder: (context, error, stackTrace) {
                  return const StatusPanel(
                    title: 'QR unavailable',
                    message: 'Open this receipt from the printed QR code.',
                  );
                },
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _TarotImage extends StatelessWidget {
  const _TarotImage({required this.tarotUrl});

  final String tarotUrl;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ClipRRect(
        borderRadius: BorderRadius.circular(2),
        child: Image.network(
          tarotUrl,
          width: 220,
          fit: BoxFit.contain,
          errorBuilder: (context, error, stackTrace) => const SizedBox.shrink(),
        ),
      ),
    );
  }
}

class _Rule extends StatelessWidget {
  const _Rule({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(height: 0.7, color: OracleColors.rule),
        const SizedBox(height: 13),
        Text(
          label,
          textAlign: TextAlign.center,
          style: GoogleFonts.cinzel(
            color: OracleColors.rust,
            fontSize: 11,
            letterSpacing: 4,
          ),
        ),
      ],
    );
  }
}
