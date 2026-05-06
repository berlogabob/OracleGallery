import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme/oracle_theme.dart';
import '../widgets/oracle_primitives.dart';

class MarksPage extends StatelessWidget {
  const MarksPage({super.key});

  static const _marks = [
    _BaseMark(
      'THE KIND SOUL',
      '../assets/symbols/test_the_kind_soul_220047_plotter.svg',
      'A soft line that keeps returning to the center.',
    ),
    _BaseMark(
      'THE BITTER ROOT',
      '../assets/symbols/20260416_213514_plotter.svg',
      'A fractured descent, pulled by certainty and fear.',
    ),
    _BaseMark(
      'THE PITIFUL STORY',
      '../assets/symbols/test_the_pitiful_story_215312_plotter.svg',
      'A hesitant shape carrying a repeated wound.',
    ),
    _BaseMark(
      'THE SHRIEK',
      '../assets/symbols/test_the_shriek_220002_plotter.svg',
      'A sharp signal, unstable and bright.',
    ),
    _BaseMark(
      'THE THORNS',
      '../assets/symbols/test_the_thorns_215209_plotter.svg',
      'A defensive rhythm built from small refusals.',
    ),
    _BaseMark(
      'THE VEIL',
      '../assets/symbols/20260420_195415_plotter.svg',
      'A partial cover, neither hidden nor revealed.',
    ),
    _BaseMark(
      'THE MIRROR',
      '../assets/symbols/20260421_195713_plotter.svg',
      'A doubled trace that answers itself.',
    ),
    _BaseMark(
      'THE SEED',
      '../assets/symbols/20260421_223735_plotter.svg',
      'A compact beginning waiting for pressure.',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return OraclePage(
      children: [
        OracleSection(
          label: 'Library',
          title: 'Eight base marks become unstable variants.',
          child: LayoutBuilder(
            builder: (context, constraints) {
              final crossAxisCount = constraints.maxWidth > 860 ? 4 : constraints.maxWidth > 560 ? 2 : 1;
              return GridView.builder(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: _marks.length,
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: crossAxisCount,
                  mainAxisSpacing: 14,
                  crossAxisSpacing: 14,
                  childAspectRatio: 1.05,
                ),
                itemBuilder: (context, index) {
                  final mark = _marks[index];
                  return _MarkCard(mark: mark);
                },
              );
            },
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
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: OracleColors.paper,
        border: Border.all(color: OracleColors.rule, width: 0.7),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 104,
            height: 104,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: OracleColors.cream,
              shape: BoxShape.circle,
              border: Border.all(color: OracleColors.goldDim, width: 0.8),
            ),
            child: SvgPicture.asset(
              mark.assetPath,
              fit: BoxFit.contain,
              colorFilter: const ColorFilter.mode(OracleColors.ink, BlendMode.srcIn),
            ),
          ),
          const SizedBox(height: 16),
          Text(mark.name, textAlign: TextAlign.center, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Text(mark.description, textAlign: TextAlign.center, style: Theme.of(context).textTheme.bodyMedium),
        ],
      ),
    );
  }
}

class _BaseMark {
  const _BaseMark(this.name, this.assetPath, this.description);

  final String name;
  final String assetPath;
  final String description;
}
