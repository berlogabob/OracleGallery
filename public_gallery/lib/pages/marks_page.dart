import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme/oracle_theme.dart';
import '../widgets/oracle_primitives.dart';

class MarksPage extends StatelessWidget {
  const MarksPage({super.key});

  static const _marks = [
    _BaseMark(
      name: 'THE KIND SOUL',
      emotion: 'Warmth',
      assetPath: '../assets/symbols/test_the_kind_soul_220047_plotter.svg',
      description:
          'Arcs ascend from a shared baseline, widening as they recede.',
      reading: 'The oracle heard warmth: a voice that was giving something.',
    ),
    _BaseMark(
      name: 'THE BITTER ROOT',
      emotion: 'Refusal',
      assetPath: '../assets/symbols/20260416_213514_plotter.svg',
      description:
          'A perimeter pulls inward, guarded by uneven crossings and pressure.',
      reading:
          'The oracle heard particularity: a refusal that is specific, not general.',
    ),
    _BaseMark(
      name: 'THE PITIFUL STORY',
      emotion: 'Weight',
      assetPath: '../assets/symbols/test_the_pitiful_story_215312_plotter.svg',
      description: 'A repeated wound rises and falls from the same held line.',
      reading:
          'The oracle heard something said more than once, returned to but not resolved.',
    ),
    _BaseMark(
      name: 'THE SHRIEK',
      emotion: 'Surprise',
      assetPath: '../assets/symbols/test_the_shriek_220002_plotter.svg',
      description:
          'A sharp signal opens from a small center and reorganises the field.',
      reading:
          'The oracle heard an opening: something that arrived without warning.',
    ),
    _BaseMark(
      name: 'THE THORNS',
      emotion: 'Defense',
      assetPath: '../assets/symbols/test_the_thorns_215209_plotter.svg',
      description: 'Small refusals repeat into a defensive rhythm.',
      reading: 'The oracle heard pressure held at the edge of the body.',
    ),
    _BaseMark(
      name: 'THE VEIL',
      emotion: 'Cover',
      assetPath: '../assets/symbols/20260420_195415_plotter.svg',
      description: 'A partial cover, neither hidden nor revealed.',
      reading: 'The oracle heard a surface that keeps part of itself withheld.',
    ),
    _BaseMark(
      name: 'THE MIRROR',
      emotion: 'Echo',
      assetPath: '../assets/symbols/20260421_195713_plotter.svg',
      description: 'A doubled trace answers itself across the same boundary.',
      reading: 'The oracle heard reflection: a voice measuring its own return.',
    ),
    _BaseMark(
      name: 'THE SEED',
      emotion: 'Beginning',
      assetPath: '../assets/symbols/20260421_223735_plotter.svg',
      description: 'A compact beginning waits inside pressure.',
      reading: 'The oracle heard a form not yet released from its container.',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return OraclePage(
      children: [
        OracleSection(
          label: 'Library',
          title:
              'These signs were once used to leave messages for those who came after.',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Did not receive your receipt? Browse the eight marks below to find yours.',
                style: Theme.of(context).textTheme.bodyLarge,
              ),
              const SizedBox(height: 26),
              LayoutBuilder(
                builder: (context, constraints) {
                  final crossAxisCount = constraints.maxWidth > 920 ? 2 : 1;
                  return GridView.builder(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: _marks.length,
                    gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: crossAxisCount,
                      mainAxisSpacing: 16,
                      crossAxisSpacing: 16,
                      childAspectRatio: constraints.maxWidth > 920
                          ? 2.35
                          : 1.35,
                    ),
                    itemBuilder: (context, index) =>
                        _MarkCard(mark: _marks[index]),
                  );
                },
              ),
              const SizedBox(height: 28),
              Text(
                'The oracle does not understand your words. It listens to the texture of your voice: pitch, energy, and rhythm. A small machine-learning model selects one of these marks, and the plotter draws it onto fabric.',
                style: Theme.of(context).textTheme.bodyLarge,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _MarkCard extends StatelessWidget {
  const _MarkCard({required this.mark});

  final _BaseMark mark;

  @override
  Widget build(BuildContext context) {
    return OracleCard(
      padding: EdgeInsets.zero,
      child: LayoutBuilder(
        builder: (context, constraints) {
          final stacked = constraints.maxWidth < 520;
          final visual = _MarkVisual(mark: mark);
          final copy = _MarkCopy(mark: mark);
          if (stacked) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(flex: 5, child: visual),
                Expanded(flex: 4, child: copy),
              ],
            );
          }
          return Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SizedBox(width: constraints.maxWidth * 0.42, child: visual),
              Expanded(child: copy),
            ],
          );
        },
      ),
    );
  }
}

class _MarkVisual extends StatelessWidget {
  const _MarkVisual({required this.mark});

  final _BaseMark mark;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: OracleColors.voidColor,
      padding: const EdgeInsets.all(22),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Expanded(
            child: SvgPicture.asset(
              mark.assetPath,
              fit: BoxFit.contain,
              colorFilter: const ColorFilter.mode(
                OracleColors.gold,
                BlendMode.srcIn,
              ),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            mark.emotion.toUpperCase(),
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              color: OracleColors.goldDim,
              fontSize: 10,
              letterSpacing: 2.4,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            mark.name,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              color: OracleColors.gold,
              fontSize: 13,
              letterSpacing: 2,
            ),
          ),
        ],
      ),
    );
  }
}

class _MarkCopy extends StatelessWidget {
  const _MarkCopy({required this.mark});

  final _BaseMark mark;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(22),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(mark.description, style: Theme.of(context).textTheme.bodyLarge),
          const SizedBox(height: 16),
          Text(
            mark.reading,
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
              color: OracleColors.inkMid,
              fontSize: 17,
              fontStyle: FontStyle.italic,
              height: 1.35,
            ),
          ),
        ],
      ),
    );
  }
}

class _BaseMark {
  const _BaseMark({
    required this.name,
    required this.emotion,
    required this.assetPath,
    required this.description,
    required this.reading,
  });

  final String name;
  final String emotion;
  final String assetPath;
  final String description;
  final String reading;
}
