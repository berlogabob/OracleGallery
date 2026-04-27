import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:flutter_web_plugins/url_strategy.dart';
import 'package:go_router/go_router.dart';

import 'firebase_config.dart';

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
    final theme = ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: const Color(0xFFF5EFE3),
      colorScheme: const ColorScheme.light(
        primary: Color(0xFF1E1B18),
        secondary: Color(0xFF9F5A26),
        surface: Colors.white,
      ),
      textTheme: const TextTheme(
        displayLarge: TextStyle(
          fontSize: 54,
          fontWeight: FontWeight.w700,
          height: 0.95,
          color: Color(0xFF1E1B18),
        ),
        headlineMedium: TextStyle(
          fontSize: 32,
          fontWeight: FontWeight.w700,
          color: Color(0xFF1E1B18),
        ),
        bodyLarge: TextStyle(
          fontSize: 16,
          height: 1.45,
          color: Color(0xFF3A332D),
        ),
      ),
    );

    return MaterialApp.router(
      title: 'Oracle Gallery',
      debugShowCheckedModeBanner: false,
      theme: theme,
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
      return const GalleryShell(
        title: 'Oracle Gallery',
        subtitle: 'Firebase config is missing in the build.',
        body: ConfigHelpCard(),
      );
    }

    final stream = FirebaseFirestore.instance
        .collection('sessions')
        .orderBy('createdAt', descending: true)
        .snapshots();

    return GalleryShell(
      title: 'Digital Oracle',
      subtitle:
          'Every session appears here as soon as the uploader publishes it.',
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
              title: 'No sessions yet',
              subtitle:
                  'As soon as a visitor finishes a dialogue, their artifact will appear here.',
            );
          }

          return Wrap(
            spacing: 20,
            runSpacing: 20,
            children: docs.map((doc) {
              final data = doc.data();
              return SessionCard(
                sessionId: data['sessionId'] as String? ?? doc.id,
                title: data['title'] as String? ?? doc.id,
                summary: data['summary'] as String? ?? '',
                previewUrl: data['previewUrl'] as String? ?? '',
                status: data['status'] as String? ?? 'publishing',
                createdAt: data['createdAt'] as String? ?? '',
              );
            }).toList(),
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
      return const GalleryShell(
        title: 'Session unavailable',
        subtitle: 'Firebase config is missing in the build.',
        body: ConfigHelpCard(),
      );
    }

    final stream = FirebaseFirestore.instance
        .collection('sessions')
        .doc(sessionId)
        .snapshots();
    return GalleryShell(
      title: 'Session Artifact',
      subtitle: 'This page is stable even if the session is still publishing.',
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
          final data = doc.data()!;
          final status = data['status'] as String? ?? 'publishing';
          if (status != 'published') {
            return PublishingState(sessionId: sessionId);
          }

          final assetUrls =
              (data['assetUrls'] as Map<String, dynamic>?) ?? const {};
          final previewUrl =
              assetUrls['preview'] as String? ??
              data['previewUrl'] as String? ??
              '';
          final svgUrl =
              assetUrls['svg'] as String? ?? data['svgUrl'] as String? ?? '';
          final qrUrl = data['qrUrl'] as String? ?? '';

          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                data['title'] as String? ?? sessionId,
                style: Theme.of(context).textTheme.displayLarge,
              ),
              const SizedBox(height: 16),
              Text(
                data['summary'] as String? ?? '',
                style: Theme.of(context).textTheme.bodyLarge,
              ),
              const SizedBox(height: 28),
              LayoutBuilder(
                builder: (context, constraints) {
                  final isWide = constraints.maxWidth >= 980;
                  final preview = PreviewPanel(
                    previewUrl: previewUrl,
                    svgUrl: svgUrl,
                  );
                  final meta = SessionMetaPanel(
                    sessionId: sessionId,
                    createdAt: data['createdAt'] as String? ?? '',
                    plotStatus: data['plotStatus'] as String? ?? 'pending',
                    qrUrl: qrUrl,
                  );
                  if (isWide) {
                    return Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(flex: 3, child: preview),
                        const SizedBox(width: 24),
                        Expanded(flex: 2, child: meta),
                      ],
                    );
                  }
                  return Column(
                    children: [preview, const SizedBox(height: 24), meta],
                  );
                },
              ),
            ],
          );
        },
      ),
    );
  }
}

class GalleryShell extends StatelessWidget {
  const GalleryShell({
    super.key,
    required this.title,
    required this.subtitle,
    required this.body,
  });

  final String title;
  final String subtitle;
  final Widget body;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [Color(0xFFF5EFE3), Color(0xFFE6D5B6)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
        ),
        child: Stack(
          children: [
            const Positioned(
              top: -120,
              right: -100,
              child: _Orb(size: 320, color: Color(0x33C36E2F)),
            ),
            const Positioned(
              left: -80,
              bottom: -60,
              child: _Orb(size: 260, color: Color(0x229E7D4F)),
            ),
            SafeArea(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 1280),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            GestureDetector(
                              onTap: () => GoRouter.of(context).go('/'),
                              child: Container(
                                width: 64,
                                height: 64,
                                decoration: BoxDecoration(
                                  color: const Color(0xFF1E1B18),
                                  borderRadius: BorderRadius.circular(18),
                                ),
                                child: const Center(
                                  child: Text(
                                    '⟡',
                                    style: TextStyle(
                                      color: Colors.white,
                                      fontSize: 28,
                                    ),
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
                                    title,
                                    style: Theme.of(
                                      context,
                                    ).textTheme.headlineMedium,
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    subtitle,
                                    style: Theme.of(
                                      context,
                                    ).textTheme.bodyLarge,
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 28),
                        body,
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class SessionCard extends StatelessWidget {
  const SessionCard({
    super.key,
    required this.sessionId,
    required this.title,
    required this.summary,
    required this.previewUrl,
    required this.status,
    required this.createdAt,
  });

  final String sessionId;
  final String title;
  final String summary;
  final String previewUrl;
  final String status;
  final String createdAt;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 340,
      child: InkWell(
        borderRadius: BorderRadius.circular(28),
        onTap: () => GoRouter.of(context).go('/session/$sessionId'),
        child: Ink(
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(28),
            boxShadow: const [
              BoxShadow(
                color: Color(0x14000000),
                blurRadius: 32,
                offset: Offset(0, 18),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ClipRRect(
                borderRadius: const BorderRadius.vertical(
                  top: Radius.circular(28),
                ),
                child: SizedBox(
                  height: 240,
                  width: double.infinity,
                  child: previewUrl.isEmpty
                      ? const _PreviewFallback()
                      : Image.network(previewUrl, fit: BoxFit.cover),
                ),
              ),
              Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _StatusChip(status: status),
                    const SizedBox(height: 12),
                    Text(
                      title,
                      style: Theme.of(
                        context,
                      ).textTheme.headlineMedium?.copyWith(fontSize: 24),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      summary.isEmpty ? 'Oracle session $sessionId' : summary,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      createdAt,
                      style: const TextStyle(
                        color: Color(0xFF6B6258),
                        fontSize: 13,
                        letterSpacing: 0.3,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class PreviewPanel extends StatelessWidget {
  const PreviewPanel({
    super.key,
    required this.previewUrl,
    required this.svgUrl,
  });

  final String previewUrl;
  final String svgUrl;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(30),
        boxShadow: const [
          BoxShadow(
            color: Color(0x14000000),
            blurRadius: 32,
            offset: Offset(0, 18),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Preview',
            style: TextStyle(
              fontSize: 14,
              letterSpacing: 1.1,
              color: Color(0xFF6B6258),
            ),
          ),
          const SizedBox(height: 12),
          AspectRatio(
            aspectRatio: 1.1,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(24),
              child: previewUrl.isEmpty
                  ? const _PreviewFallback()
                  : Image.network(previewUrl, fit: BoxFit.cover),
            ),
          ),
          const SizedBox(height: 18),
          if (svgUrl.isNotEmpty)
            Container(
              constraints: const BoxConstraints(minHeight: 320),
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(24),
                color: const Color(0xFFF7F5EF),
              ),
              child: SvgPicture.network(
                svgUrl,
                fit: BoxFit.contain,
                placeholderBuilder: (context) =>
                    const Center(child: CircularProgressIndicator()),
              ),
            ),
        ],
      ),
    );
  }
}

class SessionMetaPanel extends StatelessWidget {
  const SessionMetaPanel({
    super.key,
    required this.sessionId,
    required this.createdAt,
    required this.plotStatus,
    required this.qrUrl,
  });

  final String sessionId;
  final String createdAt;
  final String plotStatus;
  final String qrUrl;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1B18),
        borderRadius: BorderRadius.circular(30),
      ),
      child: DefaultTextStyle(
        style: const TextStyle(
          color: Color(0xFFF7F1E6),
          fontSize: 16,
          height: 1.4,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Session metadata',
              style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 18),
            _MetaLine(label: 'Session ID', value: sessionId),
            _MetaLine(label: 'Created', value: createdAt),
            _MetaLine(label: 'Plot status', value: plotStatus),
            _MetaLine(label: 'QR target', value: qrUrl),
          ],
        ),
      ),
    );
  }
}

class PublishingState extends StatelessWidget {
  const PublishingState({super.key, required this.sessionId});

  final String sessionId;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(32),
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
            'The QR code is already valid. This page will start showing the artifact as soon as Firebase receives the public files.',
            style: Theme.of(context).textTheme.bodyLarge,
          ),
          const SizedBox(height: 18),
          const LinearProgressIndicator(minHeight: 8),
        ],
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
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(28),
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
        color: Colors.white,
        borderRadius: BorderRadius.circular(28),
      ),
      child: const SelectableText(
        'Build the gallery with the required --dart-define Firebase values.\n\n'
        'Example:\n'
        'flutter build web --dart-define=FIREBASE_API_KEY=... --dart-define=FIREBASE_APP_ID=... '
        '--dart-define=FIREBASE_MESSAGING_SENDER_ID=... --dart-define=FIREBASE_PROJECT_ID=... '
        '--dart-define=FIREBASE_AUTH_DOMAIN=... --dart-define=FIREBASE_STORAGE_BUCKET=...',
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
        color: Colors.white,
        borderRadius: BorderRadius.circular(28),
      ),
      child: Text(message, style: Theme.of(context).textTheme.bodyLarge),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final isPublished = status == 'published';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: isPublished ? const Color(0xFFE9F2E3) : const Color(0xFFFFE8D7),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        status,
        style: TextStyle(
          color: isPublished
              ? const Color(0xFF325B28)
              : const Color(0xFF9F5A26),
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class _MetaLine extends StatelessWidget {
  const _MetaLine({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              color: Color(0xFFBCA88E),
              fontSize: 13,
              letterSpacing: 0.8,
            ),
          ),
          const SizedBox(height: 4),
          SelectableText(value.isEmpty ? '-' : value),
        ],
      ),
    );
  }
}

class _PreviewFallback extends StatelessWidget {
  const _PreviewFallback();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          colors: [Color(0xFFEBD8B1), Color(0xFFDDB37E)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: const Center(
        child: Text(
          'No Preview',
          style: TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.w700,
            color: Color(0xFF5B4531),
          ),
        ),
      ),
    );
  }
}

class _Orb extends StatelessWidget {
  const _Orb({required this.size, required this.color});

  final double size;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: RadialGradient(colors: [color, Colors.transparent]),
      ),
    );
  }
}
