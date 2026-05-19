import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../models/session_data.dart';
import '../theme/oracle_theme.dart';
import 'cloth_layout.dart';

class SteppedClothSurface extends StatelessWidget {
  const SteppedClothSurface({
    super.key,
    required this.sessions,
    required this.highlightSessionId,
  });

  final List<SessionData> sessions;
  final String? highlightSessionId;

  @override
  Widget build(BuildContext context) {
    final orderedSessions = sessions.reversed.toList(growable: false);
    final layout = buildClothGridLayout(orderedSessions.length);

    return LayoutBuilder(
      builder: (context, constraints) {
        final geometry = _ClothGridGeometry.fromWidth(
          maxWidth: constraints.maxWidth,
          side: layout.side,
        );

        return SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: SizedBox(
            width: geometry.surfaceWidth,
            height: geometry.surfaceHeight,
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: const Color(0xFFE6DCC7),
                border: Border.all(color: OracleColors.rule, width: 0.8),
              ),
              child: Stack(
                children: [
                  Positioned.fill(
                    child: CustomPaint(
                      painter: _SteppedClothPainter(
                        layout: layout,
                        sessions: orderedSessions,
                        highlightSessionId: highlightSessionId,
                      ),
                    ),
                  ),
                  for (final placement in layout.placements)
                    _ClothHitTarget(
                      geometry: geometry,
                      placement: placement,
                      session: orderedSessions[placement.index],
                      highlighted:
                          orderedSessions[placement.index].sessionId ==
                          highlightSessionId,
                    ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _ClothHitTarget extends StatelessWidget {
  const _ClothHitTarget({
    required this.geometry,
    required this.placement,
    required this.session,
    required this.highlighted,
  });

  final _ClothGridGeometry geometry;
  final ClothGridPlacement placement;
  final SessionData session;
  final bool highlighted;

  @override
  Widget build(BuildContext context) {
    final center = geometry.centerFor(placement);
    final targetSize = math.max(36.0, geometry.cell * 0.94);
    return Positioned(
      left: center.dx - targetSize / 2,
      top: center.dy - targetSize / 2,
      width: targetSize,
      height: targetSize,
      child: Tooltip(
        message: session.markName.isEmpty
            ? session.sessionId
            : session.markName,
        child: Semantics(
          button: true,
          label:
              'Open ${session.markName.isEmpty ? session.sessionId : session.markName}',
          selected: highlighted,
          child: MouseRegion(
            cursor: SystemMouseCursors.click,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => context.go(
                '/session/${Uri.encodeComponent(session.sessionId)}',
              ),
              child: const SizedBox.expand(),
            ),
          ),
        ),
      ),
    );
  }
}

class _SteppedClothPainter extends CustomPainter {
  const _SteppedClothPainter({
    required this.layout,
    required this.sessions,
    required this.highlightSessionId,
  });

  final ClothGridLayout layout;
  final List<SessionData> sessions;
  final String? highlightSessionId;

  @override
  void paint(Canvas canvas, Size size) {
    final geometry = _ClothGridGeometry.fromSize(size, side: layout.side);
    _paintFabric(canvas, size);

    if (layout.side == 0) {
      return;
    }

    for (final placement in layout.placements) {
      final session = sessions[placement.index];
      final highlighted = session.sessionId == highlightSessionId;
      _paintSessionCell(canvas, geometry, placement, session, highlighted);
    }
  }

  void _paintFabric(Canvas canvas, Size size) {
    final background = Paint()..color = const Color(0xFFE6DCC7);
    canvas.drawRect(Offset.zero & size, background);

    final warp = Paint()
      ..color = OracleColors.rule.withValues(alpha: 0.38)
      ..strokeWidth = 0.55;
    final weft = Paint()
      ..color = OracleColors.paper.withValues(alpha: 0.42)
      ..strokeWidth = 0.55;

    const step = 30.0;
    for (var x = -size.height * 0.08; x <= size.width; x += step) {
      canvas.drawLine(
        Offset(x, 0),
        Offset(x + size.height * 0.08, size.height),
        warp,
      );
    }
    for (var y = 0.0; y <= size.height + size.width * 0.02; y += step) {
      canvas.drawLine(
        Offset(0, y),
        Offset(size.width, y - size.width * 0.02),
        weft,
      );
    }
  }

  void _paintSessionCell(
    Canvas canvas,
    _ClothGridGeometry geometry,
    ClothGridPlacement placement,
    SessionData session,
    bool highlighted,
  ) {
    final center = geometry.centerFor(placement);
    final radius = geometry.cell * (highlighted ? 0.48 : 0.46);
    final hash = _stableHash(
      session.markName.isNotEmpty ? session.markName : session.sessionId,
    );
    final accent = highlighted ? OracleColors.rust : OracleColors.goldDim;
    final outlinePaint = Paint()
      ..color = accent.withValues(alpha: highlighted ? 0.88 : 0.54)
      ..style = PaintingStyle.stroke
      ..strokeWidth = highlighted ? 1.65 : 0.9;
    final fiberPaint = Paint()
      ..color = OracleColors.ink.withValues(alpha: highlighted ? 0.72 : 0.42)
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..strokeWidth = highlighted ? 1.35 : 0.95;

    canvas.drawCircle(center, radius, outlinePaint);
    if (highlighted) {
      canvas.drawCircle(
        center,
        radius + 5,
        Paint()
          ..color = OracleColors.gold.withValues(alpha: 0.72)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.05,
      );
    }

    _paintGlyph(canvas, center, radius * 0.66, hash, fiberPaint);
  }

  void _paintGlyph(
    Canvas canvas,
    Offset center,
    double radius,
    int hash,
    Paint paint,
  ) {
    switch (hash % 6) {
      case 0:
        canvas.drawCircle(center, radius * 0.64, paint);
        canvas.drawLine(
          Offset(center.dx - radius * 0.75, center.dy),
          Offset(center.dx + radius * 0.75, center.dy + radius * 0.28),
          paint,
        );
        return;
      case 1:
        final path = Path()
          ..moveTo(center.dx - radius, center.dy + radius * 0.45)
          ..lineTo(center.dx - radius * 0.45, center.dy - radius * 0.4)
          ..lineTo(center.dx, center.dy + radius * 0.32)
          ..lineTo(center.dx + radius * 0.45, center.dy - radius * 0.4)
          ..lineTo(center.dx + radius, center.dy + radius * 0.45);
        canvas.drawPath(path, paint);
        return;
      case 2:
        for (var index = 0; index < 8; index++) {
          final angle = (math.pi * 2 * index / 8) + ((hash % 17) * 0.01);
          canvas.drawLine(
            center,
            Offset(
              center.dx + math.cos(angle) * radius,
              center.dy + math.sin(angle) * radius,
            ),
            paint,
          );
        }
        return;
      case 3:
        canvas.drawLine(
          Offset(center.dx - radius, center.dy - radius * 0.45),
          Offset(center.dx + radius, center.dy - radius * 0.45),
          paint,
        );
        for (var index = -2; index <= 2; index++) {
          final x = center.dx + index * radius * 0.32;
          canvas.drawLine(
            Offset(x, center.dy - radius * 0.42),
            Offset(
              x + (index.isEven ? -1 : 1) * radius * 0.18,
              center.dy + radius * 0.82,
            ),
            paint,
          );
        }
        return;
      case 4:
        final rect = Rect.fromCircle(
          center: Offset(center.dx, center.dy + radius * 0.45),
          radius: radius,
        );
        canvas.drawArc(rect, math.pi * 1.08, math.pi * 0.84, false, paint);
        canvas.drawArc(
          rect.inflate(radius * 0.28),
          math.pi * 1.08,
          math.pi * 0.84,
          false,
          paint,
        );
        return;
      default:
        final path = Path()
          ..moveTo(center.dx, center.dy - radius)
          ..lineTo(center.dx + radius, center.dy)
          ..lineTo(center.dx, center.dy + radius)
          ..lineTo(center.dx - radius, center.dy)
          ..close()
          ..moveTo(center.dx - radius * 0.62, center.dy - radius * 0.62)
          ..lineTo(center.dx + radius * 0.62, center.dy + radius * 0.62)
          ..moveTo(center.dx + radius * 0.62, center.dy - radius * 0.62)
          ..lineTo(center.dx - radius * 0.62, center.dy + radius * 0.62);
        canvas.drawPath(path, paint);
        return;
    }
  }

  int _stableHash(String value) {
    var hash = 0;
    for (final unit in value.codeUnits) {
      hash = (hash * 31 + unit) & 0x7fffffff;
    }
    return hash;
  }

  @override
  bool shouldRepaint(covariant _SteppedClothPainter oldDelegate) {
    return oldDelegate.sessions != sessions ||
        oldDelegate.highlightSessionId != highlightSessionId;
  }
}

class _ClothGridGeometry {
  const _ClothGridGeometry({
    required this.surfaceWidth,
    required this.surfaceHeight,
    required this.cell,
    required this.origin,
  });

  final double surfaceWidth;
  final double surfaceHeight;
  final double cell;
  final Offset origin;

  static _ClothGridGeometry fromWidth({
    required double maxWidth,
    required int side,
  }) {
    final normalizedSide = math.max(1, side);
    const horizontalPadding = 34.0;
    const verticalPadding = 48.0;
    const minCell = 34.0;
    const maxCell = 128.0;

    final minimumWidth = normalizedSide * minCell + horizontalPadding * 2;
    final surfaceWidth = math.max(maxWidth, minimumWidth);
    final availableWidth = surfaceWidth - horizontalPadding * 2;
    final cell = math.min(maxCell, availableWidth / normalizedSide);
    final gridWidth = cell * normalizedSide;
    final surfaceHeight = math.max(420.0, gridWidth + verticalPadding * 2);

    return _ClothGridGeometry(
      surfaceWidth: surfaceWidth,
      surfaceHeight: surfaceHeight,
      cell: cell,
      origin: Offset(
        (surfaceWidth - gridWidth) / 2,
        (surfaceHeight - gridWidth) / 2,
      ),
    );
  }

  static _ClothGridGeometry fromSize(Size size, {required int side}) {
    final normalizedSide = math.max(1, side);
    const horizontalPadding = 34.0;
    const maxCell = 128.0;

    final availableWidth = math.max(0.0, size.width - horizontalPadding * 2);
    final cell = math.min(maxCell, availableWidth / normalizedSide);
    final gridWidth = cell * normalizedSide;
    return _ClothGridGeometry(
      surfaceWidth: size.width,
      surfaceHeight: size.height,
      cell: cell,
      origin: Offset(
        (size.width - gridWidth) / 2,
        (size.height - gridWidth) / 2,
      ),
    );
  }

  Offset centerFor(ClothGridPlacement placement) {
    return Offset(
      origin.dx + placement.column * cell + cell / 2,
      origin.dy + placement.row * cell + cell / 2,
    );
  }
}
