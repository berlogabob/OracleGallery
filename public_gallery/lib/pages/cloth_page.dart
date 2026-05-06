import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../models/session_data.dart';
import '../services/session_repository.dart';
import '../theme/oracle_theme.dart';
import '../widgets/oracle_primitives.dart';

class ClothPage extends StatelessWidget {
  const ClothPage({super.key, required this.firebaseReady, this.highlightSessionId});

  final bool firebaseReady;
  final String? highlightSessionId;

  @override
  Widget build(BuildContext context) {
    return OraclePage(
      children: [
        OracleSection(
          label: 'The cloth',
          title: 'A public stream of published oracle marks.',
          child: firebaseReady ? _SessionStream(highlightSessionId: highlightSessionId) : const ConfigHelpCard(),
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

  @override
  void initState() {
    super.initState();
    _lookupController = TextEditingController(text: widget.highlightSessionId ?? '');
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
      stream: SessionRepository().watchVisibleSessions(),
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return StatusPanel(title: 'Could not load the cloth', message: snapshot.error.toString());
        }
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: Padding(padding: EdgeInsets.all(28), child: CircularProgressIndicator()));
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
                message: 'Published real sessions will appear here after the uploader writes them to Firestore.',
              ),
            ],
          );
        }

        final highlighted = widget.highlightSessionId != null && sessions.any((s) => s.sessionId == widget.highlightSessionId);
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
                  message: 'Direct receipt links can open hidden or unpublished sessions, but the cloth shows only public real sessions.',
                ),
              ),
            LayoutBuilder(
              builder: (context, constraints) {
                final crossAxisCount = constraints.maxWidth > 980 ? 4 : constraints.maxWidth > 680 ? 3 : 2;
                return GridView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: sessions.length,
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: crossAxisCount,
                    mainAxisSpacing: 14,
                    crossAxisSpacing: 14,
                    childAspectRatio: 0.74,
                  ),
                  itemBuilder: (context, index) {
                    final session = sessions[index];
                    return _SessionCard(
                      session: session,
                      highlighted: session.sessionId == widget.highlightSessionId,
                    );
                  },
                );
              },
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
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: OracleColors.paper,
        border: Border.all(color: OracleColors.rule, width: 0.7),
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final narrow = constraints.maxWidth < 680;
          final count = _CountPanel(visibleCount: visibleCount);
          final lookup = _LookupPanel(controller: controller, onLookup: onLookup);
          if (narrow) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                count,
                const SizedBox(height: 14),
                lookup,
              ],
            );
          }
          return Row(
            children: [
              count,
              const SizedBox(width: 22),
              Expanded(child: lookup),
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
          style: GoogleFonts.cinzelDecorative(
            color: OracleColors.gold,
            fontSize: 34,
            letterSpacing: 4,
          ),
        ),
      ],
    );
  }
}

class _LookupPanel extends StatelessWidget {
  const _LookupPanel({required this.controller, required this.onLookup});

  final TextEditingController controller;
  final ValueChanged<String> onLookup;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: TextField(
            controller: controller,
            decoration: const InputDecoration(
              labelText: 'Find session in the cloth',
              hintText: '20260428_183129',
            ),
            onSubmitted: onLookup,
          ),
        ),
        const SizedBox(width: 12),
        FilledButton(
          onPressed: () => onLookup(controller.text),
          child: const Text('Find'),
        ),
      ],
    );
  }
}

class _SessionCard extends StatelessWidget {
  const _SessionCard({required this.session, required this.highlighted});

  final SessionData session;
  final bool highlighted;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () => context.go('/session/${session.sessionId}'),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: OracleColors.paper,
          border: Border.all(color: highlighted ? OracleColors.gold : OracleColors.rule, width: highlighted ? 1.6 : 0.7),
        ),
        child: Column(
          children: [
            SymbolNetworkView(svgUrl: session.svgUrl, size: 132),
            const SizedBox(height: 14),
            Text(
              session.markName.isEmpty ? 'UNNAMED MARK' : session.markName.toUpperCase(),
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: GoogleFonts.cinzel(color: OracleColors.ink, fontSize: 12, letterSpacing: 1.6),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: Text(
                session.oracleText,
                textAlign: TextAlign.center,
                maxLines: 5,
                overflow: TextOverflow.fade,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
