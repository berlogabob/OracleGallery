import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme/oracle_theme.dart';
import '../widgets/oracle_primitives.dart';
import '../widgets/session_lookup_field.dart';

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
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 64),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 940),
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final compact = constraints.maxWidth < 560;
                  return Column(
                    children: [
                      const _OraclePortrait(),
                      const SizedBox(height: 28),
                      Text(
                        'THE ORACLE THAT WEARS US',
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.headlineMedium
                            ?.copyWith(
                              color: OracleColors.gold,
                              fontSize: compact ? 30 : 42,
                              letterSpacing: compact ? 4 : 8,
                              height: 1.18,
                            ),
                      ),
                      const SizedBox(height: 18),
                      Text(
                        'A public cloth of generated marks, receipts, and printed fragments.',
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                          color: OracleColors.cream,
                          fontSize: compact ? 20 : 22,
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
                            style: FilledButton.styleFrom(
                              backgroundColor: OracleColors.gold,
                              foregroundColor: OracleColors.voidColor,
                              padding: const EdgeInsets.symmetric(
                                horizontal: 34,
                                vertical: 16,
                              ),
                              textStyle: GoogleFonts.ebGaramond(
                                fontSize: 19,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            child: const Text('Enter the cloth'),
                          ),
                          OutlinedButton(
                            onPressed: () => context.go('/marks'),
                            style: _heroOutlineButtonStyle(),
                            child: const Text('The marks'),
                          ),
                          OutlinedButton(
                            onPressed: () => context.go('/about'),
                            style: _heroOutlineButtonStyle(),
                            child: const Text('About'),
                          ),
                        ],
                      ),
                    ],
                  );
                },
              ),
            ),
          ),
        ),
        OracleSection(
          label: 'Find your mark',
          title: 'Open a session directly from a printed receipt.',
          child: SessionLookupField(
            controller: _sessionController,
            onLookup: _openSession,
            labelText: 'Enter your session ID',
            supportingText: 'Your session ID is printed on your receipt.',
          ),
        ),
        OracleSection(
          label: 'What the oracle is',
          title: 'A listening machine that leaves a physical trace.',
          child: Text(
            'The oracle listens to a visitor, reads the texture of the voice, and translates that encounter into one of eight marks. The public gallery keeps the safe fragment: the generated mark, its receipt, and the route back to the shared cloth.',
            style: Theme.of(context).textTheme.bodyLarge,
          ),
        ),
        OracleSection(
          label: 'The cloth preview',
          title: 'Every published mark joins the same surface.',
          voidSection: true,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const _ClothPreview(),
              const SizedBox(height: 20),
              OutlinedButton(
                onPressed: () => context.go('/cloth'),
                style: _heroOutlineButtonStyle(),
                child: const Text('View the cloth'),
              ),
            ],
          ),
        ),
      ],
    );
  }

  void _openSession(String value) {
    final sessionId = value.trim();
    if (sessionId.isNotEmpty) {
      context.go('/cloth?session=${Uri.encodeQueryComponent(sessionId)}');
    }
  }

  ButtonStyle _heroOutlineButtonStyle() {
    return OutlinedButton.styleFrom(
      foregroundColor: OracleColors.cream,
      side: const BorderSide(color: OracleColors.rule, width: 1.1),
      padding: const EdgeInsets.symmetric(horizontal: 34, vertical: 16),
      textStyle: GoogleFonts.ebGaramond(
        fontSize: 19,
        fontWeight: FontWeight.w700,
      ),
    ).copyWith(
      overlayColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.hovered) ||
            states.contains(WidgetState.pressed)) {
          return OracleColors.gold.withValues(alpha: 0.16);
        }
        return null;
      }),
    );
  }
}

class _OraclePortrait extends StatelessWidget {
  const _OraclePortrait();

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 150,
      height: 190,
      child: CustomPaint(painter: _OraclePortraitPainter()),
    );
  }
}

class _OraclePortraitPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final glow = Paint()
      ..shader = RadialGradient(
        colors: [
          OracleColors.gold.withValues(alpha: 0.48),
          OracleColors.gold.withValues(alpha: 0.08),
          Colors.transparent,
        ],
      ).createShader(Offset.zero & size);
    canvas.drawOval(
      Rect.fromCenter(center: center, width: size.width, height: size.height),
      glow,
    );

    final stroke = Paint()
      ..color = OracleColors.gold
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4
      ..strokeCap = StrokeCap.round;
    final path = Path()
      ..moveTo(size.width * 0.5, size.height * 0.1)
      ..cubicTo(
        size.width * 0.2,
        size.height * 0.26,
        size.width * 0.24,
        size.height * 0.6,
        size.width * 0.5,
        size.height * 0.9,
      )
      ..cubicTo(
        size.width * 0.76,
        size.height * 0.6,
        size.width * 0.8,
        size.height * 0.26,
        size.width * 0.5,
        size.height * 0.1,
      );
    canvas.drawPath(path, stroke);
    canvas.drawCircle(
      Offset(size.width * 0.5, size.height * 0.35),
      size.width * 0.16,
      stroke,
    );
    canvas.drawLine(
      Offset(size.width * 0.28, size.height * 0.64),
      Offset(size.width * 0.72, size.height * 0.64),
      stroke,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _ClothPreview extends StatelessWidget {
  const _ClothPreview();

  @override
  Widget build(BuildContext context) {
    return OracleCard.accent(
      height: 190,
      width: double.infinity,
      borderColor: OracleColors.goldDim,
      borderWidth: 0.7,
      padding: EdgeInsets.zero,
      child: CustomPaint(painter: _ClothPreviewPainter()),
    );
  }
}

class _ClothPreviewPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = OracleColors.gold.withValues(alpha: 0.58)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.8;
    const cols = 14;
    const rows = 4;
    final cellW = size.width / (cols + 1);
    final cellH = size.height / (rows + 1);
    for (var row = 0; row < rows; row++) {
      for (var col = 0; col < cols; col++) {
        final center = Offset((col + 1) * cellW, (row + 1) * cellH);
        canvas.drawCircle(center, 12, paint);
        canvas.drawLine(
          center.translate(-7, -3),
          center.translate(7, 5),
          paint,
        );
      }
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
