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
            _ClothSurface(
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
                Row(
                  children: [
                    Expanded(child: count),
                    const _SecretDebugButton(),
                  ],
                ),
                const SizedBox(height: 14),
                lookup,
              ],
            );
          }
          return Row(
            children: [
              count,
              const SizedBox(width: 10),
              const _SecretDebugButton(),
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

class _SecretDebugButton extends StatelessWidget {
  const _SecretDebugButton();

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: 'Debug sessions',
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onLongPress: () => context.go('/debug/sessions'),
        onDoubleTap: () => context.go('/debug/sessions'),
        child: const SizedBox(
          width: 22,
          height: 22,
          child: Center(
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: OracleColors.rule,
                shape: BoxShape.circle,
              ),
              child: SizedBox(width: 6, height: 6),
            ),
          ),
        ),
      ),
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

class _ClothSurface extends StatelessWidget {
  const _ClothSurface({required this.sessions, required this.highlightSessionId});

  final List<SessionData> sessions;
  final String? highlightSessionId;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        final columns = width >= 1080 ? 8 : width >= 860 ? 7 : width >= 640 ? 5 : 3;
        final cell = width / columns;
        final rows = (sessions.length / columns).ceil().clamp(2, 1000);
        final height = (rows * cell * 0.82) + 80;

        return Container(
          constraints: BoxConstraints(minHeight: height),
          decoration: BoxDecoration(
            color: OracleColors.paper,
            border: Border.all(color: OracleColors.rule, width: 0.8),
          ),
          child: Stack(
            children: [
              Positioned.fill(child: CustomPaint(painter: _ClothWeavePainter())),
              for (var index = 0; index < sessions.length; index++)
                _ClothMark(
                  session: sessions[index],
                  index: index,
                  columns: columns,
                  cell: cell,
                  highlighted: sessions[index].sessionId == highlightSessionId,
                ),
            ],
          ),
        );
      },
    );
  }
}

class _ClothMark extends StatelessWidget {
  const _ClothMark({
    required this.session,
    required this.index,
    required this.columns,
    required this.cell,
    required this.highlighted,
  });

  final SessionData session;
  final int index;
  final int columns;
  final double cell;
  final bool highlighted;

  @override
  Widget build(BuildContext context) {
    final row = index ~/ columns;
    final column = index % columns;
    final offsetX = row.isOdd ? cell * 0.44 : 0.0;
    final jitterX = ((index * 37) % 17 - 8).toDouble();
    final jitterY = ((index * 29) % 19 - 9).toDouble();
    final size = cell * (highlighted ? 0.82 : 0.66);
    final left = 28 + (column * cell) + offsetX + jitterX;
    final top = 36 + (row * cell * 0.82) + jitterY;

    return Positioned(
      left: left,
      top: top,
      width: size,
      height: size + 32,
      child: Tooltip(
        message: session.markName.isEmpty ? session.sessionId : session.markName,
        child: InkWell(
          borderRadius: BorderRadius.circular(size),
          onTap: () => context.go('/session/${session.sessionId}'),
          child: Column(
            children: [
              AnimatedContainer(
                duration: const Duration(milliseconds: 180),
                padding: EdgeInsets.all(highlighted ? 6 : 10),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: highlighted ? OracleColors.gold : OracleColors.rule,
                    width: highlighted ? 1.6 : 0.7,
                  ),
                  color: OracleColors.cream.withValues(alpha: highlighted ? 0.95 : 0.54),
                ),
                child: SymbolNetworkView(svgUrl: session.svgUrl, size: size - 22),
              ),
              if (highlighted) ...[
                const SizedBox(height: 6),
                Text(
                  'FOUND',
                  style: GoogleFonts.cinzel(
                    color: OracleColors.rust,
                    fontSize: 9,
                    letterSpacing: 2,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _ClothWeavePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final linePaint = Paint()
      ..color = OracleColors.rule.withValues(alpha: 0.28)
      ..strokeWidth = 0.6;
    const step = 38.0;
    for (var x = 0.0; x <= size.width; x += step) {
      canvas.drawLine(Offset(x, 0), Offset(x + (size.height * 0.06), size.height), linePaint);
    }
    for (var y = 0.0; y <= size.height; y += step) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y + (size.width * 0.018)), linePaint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
