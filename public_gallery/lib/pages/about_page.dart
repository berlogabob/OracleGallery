import 'package:flutter/material.dart';

import '../theme/oracle_theme.dart';
import '../widgets/oracle_primitives.dart';

class AboutPage extends StatelessWidget {
  const AboutPage({super.key});

  @override
  Widget build(BuildContext context) {
    return OraclePage(
      children: [
        OracleSection(
          label: 'Project',
          title: 'The oracle listens, measures instability, and leaves a mark.',
          child: Text(
            'The Oracle That Wears Us is an installation system for a local conversation, a generated receipt, and a plotted mark. Each visitor creates a short local session. The public site shows only the safe public fragment: the generated SVG mark, the receipt text, and the route back to the shared cloth.',
            style: Theme.of(context).textTheme.bodyLarge,
          ),
        ),
        OracleSection(
          label: 'Video',
          title: 'Inside the installation.',
          child: OracleCard(
            height: 360,
            alignment: Alignment.center,
            padding: EdgeInsets.zero,
            child: Text(
              'VIDEO DOCUMENTATION',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                color: OracleColors.inkMuted,
                fontSize: 12,
                letterSpacing: 3,
              ),
            ),
          ),
        ),
        OracleSection(
          label: 'How it works',
          title:
              'TouchDesigner produces the folder; Python publishes; the plotter draws.',
          child: const _ProcessSteps(),
        ),
        OracleSection(
          label: 'Privacy',
          title: 'No visitor photos, audio, or transcripts are shown here.',
          child: Text(
            'The gallery displays the public mark and the edited receipt fields only. Raw session material remains outside the public Firebase contract, and production decisions stay in the local operator GUI.',
            style: Theme.of(context).textTheme.bodyLarge,
          ),
        ),
      ],
    );
  }
}

class _ProcessSteps extends StatelessWidget {
  const _ProcessSteps();

  static const steps = [
    (
      '01',
      'Listen',
      'The oracle records the voice locally during the encounter.',
    ),
    ('02', 'Transcribe', 'Offline speech-to-text writes down what was said.'),
    ('03', 'Reply', 'A local language model composes the next oracle prompt.'),
    ('04', 'Read the voice', 'A small model reads pitch, energy, and rhythm.'),
    (
      '05',
      'Choose a mark',
      'The system maps the acoustic signature to one of eight marks.',
    ),
    (
      '06',
      'Draw',
      'A CNC plotter inscribes the mark and the thermal printer produces a receipt.',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final step in steps)
          Container(
            padding: const EdgeInsets.symmetric(vertical: 14),
            decoration: const BoxDecoration(
              border: Border(
                bottom: BorderSide(color: OracleColors.rule, width: 0.5),
              ),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 48,
                  child: Text(
                    step.$1,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: OracleColors.rust,
                      fontSize: 12,
                      letterSpacing: 2,
                    ),
                  ),
                ),
                Expanded(
                  child: RichText(
                    text: TextSpan(
                      style: Theme.of(context).textTheme.bodyLarge,
                      children: [
                        TextSpan(
                          text: '${step.$2}: ',
                          style: Theme.of(context).textTheme.titleMedium
                              ?.copyWith(
                                color: OracleColors.ink,
                                fontSize: 13,
                                letterSpacing: 1.4,
                              ),
                        ),
                        TextSpan(text: step.$3),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        const SizedBox(height: 22),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: const [
            _SystemPill('Vosk'),
            _SystemPill('Ollama'),
            _SystemPill('RAVDESS'),
            _SystemPill('ONNX'),
            _SystemPill('KittenTTS'),
          ],
        ),
      ],
    );
  }
}

class _SystemPill extends StatelessWidget {
  const _SystemPill(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return OracleCard(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
      color: Colors.transparent,
      child: Text(
        label.toUpperCase(),
        style: Theme.of(context).textTheme.titleMedium?.copyWith(
          color: OracleColors.inkMuted,
          fontSize: 10,
          letterSpacing: 1.8,
        ),
      ),
    );
  }
}
