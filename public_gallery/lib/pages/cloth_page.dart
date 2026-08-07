import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../models/session_data.dart';
import '../services/session_repository.dart';
import '../theme/oracle_theme.dart';
import '../widgets/oracle_primitives.dart';
import '../widgets/session_lookup_field.dart';
import '../widgets/stepped_cloth_surface.dart';

class ClothPage extends StatelessWidget {
  const ClothPage({
    super.key,
    required this.firebaseReady,
    this.highlightSessionId,
  });

  final bool firebaseReady;
  final String? highlightSessionId;

  @override
  Widget build(BuildContext context) {
    return OraclePage(
      children: [
        OracleSection(
          label: 'The cloth',
          title: 'A public stream of published oracle marks.',
          child: firebaseReady
              ? _SessionStream(highlightSessionId: highlightSessionId)
              : const ConfigHelpCard(),
        ),
      ],
    );
  }
}

class _SessionStream extends StatefulWidget {
  const _SessionStream({required this.highlightSessionId});

  final String? highlightSessionId;

  @override
  State<_SessionStream> createState() => _SessionStreamState();
}

class _SessionStreamState extends State<_SessionStream> {
  late final TextEditingController _lookupController;
  final Stream<List<SessionData>> _sessions = SessionRepository()
      .watchVisibleSessions();

  @override
  void initState() {
    super.initState();
    _lookupController = TextEditingController(
      text: widget.highlightSessionId ?? '',
    );
  }

  @override
  void didUpdateWidget(covariant _SessionStream oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.highlightSessionId != widget.highlightSessionId) {
      _lookupController.text = widget.highlightSessionId ?? '';
    }
  }

  @override
  void dispose() {
    _lookupController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<List<SessionData>>(
      stream: _sessions,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return StatusPanel(
            title: 'Could not load the cloth',
            message: snapshot.error.toString(),
          );
        }
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(28),
              child: CircularProgressIndicator(),
            ),
          );
        }

        final sessions = snapshot.data ?? const <SessionData>[];
        if (sessions.isEmpty) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _ClothToolbar(
                visibleCount: 0,
                controller: _lookupController,
                onLookup: _openLookup,
              ),
              const SizedBox(height: 18),
              const StatusPanel(
                title: 'The cloth is empty',
                message:
                    'Published real sessions will appear here after the uploader writes them to Firestore.',
              ),
            ],
          );
        }

        SessionData? highlightedSession;
        if (widget.highlightSessionId != null) {
          for (final session in sessions) {
            if (session.sessionId == widget.highlightSessionId) {
              highlightedSession = session;
              break;
            }
          }
        }
        final highlighted = highlightedSession != null;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _ClothToolbar(
              visibleCount: sessions.length,
              controller: _lookupController,
              onLookup: _openLookup,
            ),
            const SizedBox(height: 18),
            if (widget.highlightSessionId != null && !highlighted)
              const Padding(
                padding: EdgeInsets.only(bottom: 18),
                child: StatusPanel(
                  title: 'Session is not visible in the cloth yet',
                  message:
                      'Direct receipt links can open hidden or unpublished sessions, but the cloth shows only public real sessions.',
                ),
              ),
            if (highlightedSession != null) ...[
              _HighlightedSessionPanel(session: highlightedSession),
              const SizedBox(height: 18),
            ],
            SteppedClothSurface(
              sessions: sessions,
              highlightSessionId: widget.highlightSessionId,
            ),
          ],
        );
      },
    );
  }

  void _openLookup(String rawValue) {
    final sessionId = rawValue.trim();
    if (sessionId.isEmpty) {
      context.go('/cloth');
      return;
    }
    context.go('/cloth?session=${Uri.encodeQueryComponent(sessionId)}');
  }
}

class _ClothToolbar extends StatelessWidget {
  const _ClothToolbar({
    required this.visibleCount,
    required this.controller,
    required this.onLookup,
  });

  final int visibleCount;
  final TextEditingController controller;
  final ValueChanged<String> onLookup;

  @override
  Widget build(BuildContext context) {
    return OracleCard(
      padding: const EdgeInsets.all(18),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final narrow = constraints.maxWidth < 680;
          final count = _CountPanel(visibleCount: visibleCount);
          final lookup = SessionLookupField(
            controller: controller,
            onLookup: onLookup,
            labelText: 'Find session in the cloth',
          );
          if (narrow) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                count,
                const SizedBox(height: 14),
                lookup,
                const SizedBox(height: 8),
                const _BrowseMarksHint(),
              ],
            );
          }
          return Row(
            children: [
              count,
              const SizedBox(width: 22),
              Expanded(child: lookup),
              const SizedBox(width: 18),
              const _BrowseMarksHint(),
            ],
          );
        },
      ),
    );
  }
}

class _CountPanel extends StatelessWidget {
  const _CountPanel({required this.visibleCount});

  final int visibleCount;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('VISIBLE MARKS', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 4),
        Text(
          visibleCount.toString().padLeft(3, '0'),
          style: Theme.of(context).textTheme.displayLarge?.copyWith(
            color: OracleColors.gold,
            fontSize: 34,
            letterSpacing: 4,
          ),
        ),
      ],
    );
  }
}

class _BrowseMarksHint extends StatelessWidget {
  const _BrowseMarksHint();

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: () => context.go('/marks'),
      child: const Text('Browse marks'),
    );
  }
}

class _HighlightedSessionPanel extends StatelessWidget {
  const _HighlightedSessionPanel({required this.session});

  final SessionData session;

  @override
  Widget build(BuildContext context) {
    return OracleCard.accent(
      child: LayoutBuilder(
        builder: (context, constraints) {
          final compact = constraints.maxWidth < 640;
          final mark = SymbolNetworkView(
            svgUrl: session.svgUrl,
            size: compact ? 96 : 132,
          );
          final details = Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                session.displayName.toUpperCase(),
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: OracleColors.gold,
                  fontSize: 14,
                  letterSpacing: 2.2,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                session.oracleText.isEmpty
                    ? 'The oracle has not spoken yet.'
                    : session.oracleText,
                style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: OracleColors.cream,
                  fontSize: 18,
                  fontStyle: FontStyle.italic,
                  height: 1.35,
                ),
              ),
              const SizedBox(height: 14),
              OutlinedButton(
                onPressed: () => context.go(
                  '/session/${Uri.encodeComponent(session.sessionId)}',
                ),
                style: OutlinedButton.styleFrom(
                  foregroundColor: OracleColors.gold,
                  side: const BorderSide(color: OracleColors.goldDim),
                ),
                child: const Text('Open receipt'),
              ),
            ],
          );
          if (compact) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Center(child: mark),
                const SizedBox(height: 16),
                details,
              ],
            );
          }
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              mark,
              const SizedBox(width: 22),
              Expanded(child: details),
            ],
          );
        },
      ),
    );
  }
}
