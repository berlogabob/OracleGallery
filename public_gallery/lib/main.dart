import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:flutter_web_plugins/url_strategy.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import 'firebase_config.dart';

const _cream = Color(0xFFF7F4EF);
const _paper = Color(0xFFFBF8F1);
const _charcoal = Color(0xFF1A1A1A);
const _charcoalMid = Color(0xFF3A3A3A);
const _charcoalMuted = Color(0xFF6A6A6A);
const _rust = Color(0xFF8B4513);
const _gold = Color(0xFFC9A84C);
const _goldDim = Color(0xFF8A6F2E);
const _rule = Color(0xFFCCC5B8);
const _void = Color(0xFF0A0A12);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  setUrlStrategy(HashUrlStrategy());
  final firebaseOptions = await GalleryFirebaseConfig.load();
  if (firebaseOptions != null) {
    await Firebase.initializeApp(options: firebaseOptions);
  }
  runApp(OracleGalleryApp(firebaseReady: firebaseOptions != null));
}

class OracleGalleryApp extends StatelessWidget {
  OracleGalleryApp({super.key, required this.firebaseReady});

  final bool firebaseReady;

  late final GoRouter _router = GoRouter(
    routes: [
      GoRoute(
        path: '/',
        builder: (context, state) =>
            SessionListScreen(firebaseReady: firebaseReady),
      ),
      GoRoute(
        path: '/session/:sessionId',
        builder: (context, state) => SessionDetailScreen(
          firebaseReady: firebaseReady,
          sessionId: state.pathParameters['sessionId'] ?? '',
        ),
      ),
    ],
  );

  @override
  Widget build(BuildContext context) {
    final bodyFont = GoogleFonts.ebGaramondTextTheme();
    return MaterialApp.router(
      title: 'Oracle Gallery',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        scaffoldBackgroundColor: _cream,
        colorScheme: const ColorScheme.light(
          primary: _charcoal,
          secondary: _rust,
          surface: _paper,
        ),
        textTheme: bodyFont.copyWith(
          displayLarge: GoogleFonts.cinzel(
            fontSize: 42,
            letterSpacing: 8,
            color: _charcoal,
            fontWeight: FontWeight.w400,
          ),
          headlineMedium: GoogleFonts.cinzel(
            fontSize: 18,
            letterSpacing: 4,
            color: _charcoal,
            fontWeight: FontWeight.w400,
          ),
          bodyLarge: GoogleFonts.ebGaramond(
            fontSize: 18,
            height: 1.55,
            color: _charcoalMid,
          ),
          bodyMedium: GoogleFonts.ebGaramond(
            fontSize: 15,
            height: 1.45,
            color: _charcoalMuted,
          ),
        ),
      ),
      routerConfig: _router,
    );
  }
}

class SessionListScreen extends StatelessWidget {
  const SessionListScreen({super.key, required this.firebaseReady});

  final bool firebaseReady;

  @override
  Widget build(BuildContext context) {
    if (!firebaseReady) {
      return const OracleShell(
        eyebrow: 'CONFIGURATION',
        title: 'Oracle',
        subtitle: 'Firebase config is missing in the build.',
        body: ConfigHelpCard(),
      );
    }

    final stream = FirebaseFirestore.instance
        .collection('sessions')
        .orderBy('createdAt', descending: true)
        .snapshots();

    return OracleShell(
      eyebrow: 'THE PUBLIC REGISTER',
      title: 'Oracle',
      subtitle: 'Every published mark appears here without visitor photos.',
      body: StreamBuilder<QuerySnapshot<Map<String, dynamic>>>(
        stream: stream,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return ErrorCard(message: snapshot.error.toString());
          }
          if (!snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final docs = snapshot.data!.docs;
          if (docs.isEmpty) {
            return const EmptyState(
              title: 'No marks yet',
              subtitle:
                  'The register will fill when the uploader publishes sessions.',
            );
          }

          return Wrap(
            spacing: 18,
            runSpacing: 18,
            children: docs
                .map((doc) => SessionCard(session: SessionData.fromDoc(doc)))
                .toList(),
          );
        },
      ),
    );
  }
}

class SessionDetailScreen extends StatelessWidget {
  const SessionDetailScreen({
    super.key,
    required this.firebaseReady,
    required this.sessionId,
  });

  final bool firebaseReady;
  final String sessionId;

  @override
  Widget build(BuildContext context) {
    if (!firebaseReady) {
      return const OracleShell(
        eyebrow: 'CONFIGURATION',
        title: 'Session',
        subtitle: 'Firebase config is missing in the build.',
        body: ConfigHelpCard(),
      );
    }

    final stream = FirebaseFirestore.instance
        .collection('sessions')
        .doc(sessionId)
        .snapshots();

    return OracleShell(
      eyebrow: 'THE FRAGMENT REMAINS',
      title: 'Receipt',
      subtitle: 'A digital copy of the mark named by the oracle.',
      body: StreamBuilder<DocumentSnapshot<Map<String, dynamic>>>(
        stream: stream,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return ErrorCard(message: snapshot.error.toString());
          }
          if (!snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final doc = snapshot.data!;
          if (!doc.exists) {
            return PublishingState(sessionId: sessionId);
          }
          final session = SessionData.fromDoc(doc);
          if (session.status != 'published') {
            return PublishingState(sessionId: sessionId);
          }
          return Center(child: ReceiptCard(session: session));
        },
      ),
    );
  }
}

class SessionData {
  const SessionData({
    required this.sessionId,
    required this.createdAt,
    required this.status,
    required this.plotStatus,
    required this.markName,
    required this.oracleText,
    required this.themes,
    required this.measures,
    required this.svgUrl,
    required this.receiptUrl,
    required this.qrUrl,
  });

  final String sessionId;
  final Object? createdAt;
  final String status;
  final String plotStatus;
  final String markName;
  final String oracleText;
  final List<String> themes;
  final Map<String, double> measures;
  final String svgUrl;
  final String receiptUrl;
  final String qrUrl;

  factory SessionData.fromDoc(DocumentSnapshot<Map<String, dynamic>> doc) {
    final data = doc.data() ?? const <String, dynamic>{};
    final assetUrls = (data['assetUrls'] as Map<String, dynamic>?) ?? const {};
    return SessionData(
      sessionId: data['sessionId'] as String? ?? doc.id,
      createdAt: data['createdAt'],
      status: data['status'] as String? ?? 'publishing',
      plotStatus: data['plotStatus'] as String? ?? 'pending',
      markName:
          data['markName'] as String? ??
          data['title'] as String? ??
          doc.id.replaceAll('_', ' '),
      oracleText:
          data['oracleText'] as String? ??
          data['summary'] as String? ??
          'The oracle has not spoken yet.',
      themes: _stringList(data['themes']),
      measures: _measuresMap(data['measures']),
      svgUrl: assetUrls['svg'] as String? ?? data['svgUrl'] as String? ?? '',
      receiptUrl:
          assetUrls['receipt'] as String? ??
          data['receiptUrl'] as String? ??
          '',
      qrUrl: data['qrUrl'] as String? ?? '',
    );
  }
}

class OracleShell extends StatelessWidget {
  const OracleShell({
    super.key,
    required this.eyebrow,
    required this.title,
    required this.subtitle,
    required this.body,
  });

  final String eyebrow;
  final String title;
  final String subtitle;
  final Widget body;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: DecoratedBox(
        decoration: const BoxDecoration(color: _cream),
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 22),
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1180),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _Header(eyebrow: eyebrow, title: title, subtitle: subtitle),
                    const SizedBox(height: 28),
                    body,
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({
    required this.eyebrow,
    required this.title,
    required this.subtitle,
  });

  final String eyebrow;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: () => GoRouter.of(context).go('/'),
          child: Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: _void,
              border: Border.all(color: _goldDim, width: 0.6),
            ),
            alignment: Alignment.center,
            child: Text(
              'O',
              style: GoogleFonts.cinzel(
                color: _gold,
                fontSize: 18,
                letterSpacing: 2,
              ),
            ),
          ),
        ),
        const SizedBox(width: 18),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                eyebrow,
                style: GoogleFonts.cinzel(
                  color: _rust,
                  fontSize: 9,
                  letterSpacing: 4,
                ),
              ),
              const SizedBox(height: 6),
              Text(title, style: Theme.of(context).textTheme.headlineMedium),
              const SizedBox(height: 4),
              Text(subtitle, style: Theme.of(context).textTheme.bodyMedium),
            ],
          ),
        ),
      ],
    );
  }
}

class SessionCard extends StatelessWidget {
  const SessionCard({super.key, required this.session});

  final SessionData session;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 350,
      child: InkWell(
        onTap: () => GoRouter.of(context).go('/session/${session.sessionId}'),
        child: Ink(
          padding: const EdgeInsets.all(22),
          decoration: BoxDecoration(
            color: _paper,
            border: Border.all(color: _rule, width: 0.6),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _TinyLabel(text: _formatOracleDate(session.createdAt)),
              const SizedBox(height: 14),
              SizedBox(
                height: 120,
                child: Center(child: SymbolView(svgUrl: session.svgUrl)),
              ),
              const SizedBox(height: 16),
              Text(
                session.markName,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: GoogleFonts.cinzel(
                  fontSize: 17,
                  letterSpacing: 3,
                  color: _charcoal,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                session.oracleText,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: GoogleFonts.ebGaramond(
                  fontSize: 17,
                  height: 1.35,
                  fontStyle: FontStyle.italic,
                  color: _charcoalMid,
                ),
              ),
              const SizedBox(height: 16),
              _StatusLine(status: session.plotStatus),
            ],
          ),
        ),
      ),
    );
  }
}

class ReceiptCard extends StatelessWidget {
  const ReceiptCard({super.key, required this.session});

  final SessionData session;

  @override
  Widget build(BuildContext context) {
    final dateText = _formatOracleDate(session.createdAt);
    return Container(
      width: double.infinity,
      constraints: const BoxConstraints(maxWidth: 560),
      padding: const EdgeInsets.symmetric(horizontal: 34, vertical: 44),
      decoration: BoxDecoration(
        color: _paper,
        border: Border.all(color: _rule, width: 0.8),
        boxShadow: const [
          BoxShadow(
            color: Color(0x14000000),
            blurRadius: 34,
            offset: Offset(0, 18),
          ),
        ],
      ),
      child: Column(
        children: [
          Text(
            'THE ORACLE',
            textAlign: TextAlign.center,
            style: GoogleFonts.cinzel(
              color: _goldDim,
              fontSize: 20,
              letterSpacing: 8,
            ),
          ),
          const SizedBox(height: 10),
          Text(
            dateText,
            textAlign: TextAlign.center,
            style: GoogleFonts.cinzel(
              color: _charcoalMuted,
              fontSize: 11,
              letterSpacing: 5,
            ),
          ),
          const ReceiptRule(height: 34),
          const _TinyLabel(text: 'THE MARK'),
          const SizedBox(height: 18),
          SizedBox(
            height: 125,
            child: Center(child: SymbolView(svgUrl: session.svgUrl)),
          ),
          const SizedBox(height: 28),
          Text(
            session.markName,
            textAlign: TextAlign.center,
            style: GoogleFonts.cinzel(
              color: _charcoal,
              fontSize: 23,
              letterSpacing: 4.5,
            ),
          ),
          const ReceiptRule(height: 34),
          const _TinyLabel(text: 'WHAT THE ORACLE PERCEIVED'),
          const SizedBox(height: 12),
          Text(
            session.oracleText,
            textAlign: TextAlign.center,
            style: GoogleFonts.ebGaramond(
              color: _charcoal,
              fontSize: 20,
              fontStyle: FontStyle.italic,
              height: 1.45,
            ),
          ),
          const ReceiptRule(height: 34),
          const _TinyLabel(text: 'WHAT THE SYSTEM MEASURED'),
          const SizedBox(height: 16),
          _MeasureRows(measures: session.measures),
          const ReceiptRule(height: 34),
          const _TinyLabel(text: 'THEMES'),
          const SizedBox(height: 12),
          Text(
            _themesText(session.themes),
            textAlign: TextAlign.center,
            style: GoogleFonts.cinzel(
              color: _charcoal,
              fontSize: 16,
              letterSpacing: 4,
            ),
          ),
          const ReceiptRule(height: 34),
          _StatusLine(status: session.plotStatus),
          const SizedBox(height: 18),
          Text(
            'This fragment remains.',
            textAlign: TextAlign.center,
            style: GoogleFonts.ebGaramond(
              color: _goldDim,
              fontSize: 18,
              fontStyle: FontStyle.italic,
            ),
          ),
        ],
      ),
    );
  }
}

class SymbolView extends StatelessWidget {
  const SymbolView({super.key, required this.svgUrl});

  final String svgUrl;

  @override
  Widget build(BuildContext context) {
    if (svgUrl.isEmpty) {
      return Text(
        'SYMBOL PUBLISHING',
        style: GoogleFonts.cinzel(
          color: _charcoalMuted,
          fontSize: 10,
          letterSpacing: 3,
        ),
      );
    }
    return SvgPicture.network(
      svgUrl,
      fit: BoxFit.contain,
      colorFilter: const ColorFilter.mode(_charcoal, BlendMode.srcIn),
      placeholderBuilder: (context) => const SizedBox(
        width: 24,
        height: 24,
        child: CircularProgressIndicator(strokeWidth: 1.2),
      ),
    );
  }
}

class _MeasureRows extends StatelessWidget {
  const _MeasureRows({required this.measures});

  final Map<String, double> measures;

  @override
  Widget build(BuildContext context) {
    final rows = [
      ('VOICE INTENSITY', measures['intensity']),
      ('INSTABILITY', measures['instability']),
      ('CONFIDENCE', measures['confidence']),
    ];
    return Column(
      children: rows
          .map(
            (row) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  SizedBox(
                    width: 170,
                    child: Text(
                      row.$1,
                      textAlign: TextAlign.right,
                      style: GoogleFonts.cinzel(
                        color: _charcoal,
                        fontSize: 12,
                        letterSpacing: 2,
                      ),
                    ),
                  ),
                  const SizedBox(width: 24),
                  SizedBox(
                    width: 54,
                    child: Text(
                      row.$2 == null ? '-' : row.$2!.toStringAsFixed(2),
                      style: GoogleFonts.cinzel(
                        color: _charcoal,
                        fontSize: 12,
                        letterSpacing: 2,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          )
          .toList(),
    );
  }
}

class ReceiptRule extends StatelessWidget {
  const ReceiptRule({super.key, required this.height});

  final double height;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: height / 2),
      child: Container(height: 0.7, color: _rule),
    );
  }
}

class _TinyLabel extends StatelessWidget {
  const _TinyLabel({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      textAlign: TextAlign.center,
      style: GoogleFonts.cinzel(color: _rust, fontSize: 11, letterSpacing: 5),
    );
  }
}

class _StatusLine extends StatelessWidget {
  const _StatusLine({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    return Text(
      'PRINT STATUS: ${status.toUpperCase()}',
      textAlign: TextAlign.center,
      style: GoogleFonts.cinzel(
        color: _charcoalMuted,
        fontSize: 10,
        letterSpacing: 3,
      ),
    );
  }
}

class PublishingState extends StatelessWidget {
  const PublishingState({super.key, required this.sessionId});

  final String sessionId;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        constraints: const BoxConstraints(maxWidth: 560),
        padding: const EdgeInsets.all(32),
        decoration: BoxDecoration(
          color: _paper,
          border: Border.all(color: _rule, width: 0.7),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Session $sessionId is still publishing',
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 12),
            Text(
              'The QR code is already valid. This page will fill itself when Firebase receives the SVG and receipt text.',
              style: Theme.of(context).textTheme.bodyLarge,
            ),
            const SizedBox(height: 18),
            const LinearProgressIndicator(minHeight: 2),
          ],
        ),
      ),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.title, required this.subtitle});

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 620),
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        color: _paper,
        border: Border.all(color: _rule, width: 0.7),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: 8),
          Text(subtitle, style: Theme.of(context).textTheme.bodyLarge),
        ],
      ),
    );
  }
}

class ConfigHelpCard extends StatelessWidget {
  const ConfigHelpCard({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        color: _paper,
        border: Border.all(color: _rule, width: 0.7),
      ),
      child: const SelectableText(
        'Firebase config is loaded from web/firebase-config.json in development and docs/firebase-config.json in the published GitHub Pages build.',
      ),
    );
  }
}

class ErrorCard extends StatelessWidget {
  const ErrorCard({super.key, required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        color: _paper,
        border: Border.all(color: _rule, width: 0.7),
      ),
      child: Text(message, style: Theme.of(context).textTheme.bodyLarge),
    );
  }
}

List<String> _stringList(Object? value) {
  if (value is Iterable) {
    return value
        .map((item) => item.toString())
        .where((item) => item.isNotEmpty)
        .toList();
  }
  return const [];
}

Map<String, double> _measuresMap(Object? value) {
  if (value is! Map) {
    return const {};
  }
  final parsed = <String, double>{};
  for (final entry in value.entries) {
    final rawValue = entry.value;
    final measure = rawValue is num
        ? rawValue.toDouble()
        : double.tryParse(rawValue.toString());
    if (measure != null) {
      parsed[entry.key.toString()] = measure;
    }
  }
  return parsed;
}

String _themesText(List<String> themes) {
  if (themes.isEmpty) {
    return '-';
  }
  return themes.map((theme) => theme.toUpperCase()).join(' . ');
}

String _formatOracleDate(Object? value) {
  DateTime? date;
  if (value is Timestamp) {
    date = value.toDate();
  } else if (value is String) {
    date = DateTime.tryParse(value);
  }
  if (date == null) {
    return '-';
  }
  final local = date.toLocal();
  return '${_two(local.day)} . ${_two(local.month)} . ${local.year} . ${_two(local.hour)}:${_two(local.minute)}';
}

String _two(int value) => value.toString().padLeft(2, '0');
