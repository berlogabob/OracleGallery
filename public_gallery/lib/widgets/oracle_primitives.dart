import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme/oracle_theme.dart';

class OraclePage extends StatelessWidget {
  const OraclePage({super.key, required this.children, this.voidHeader = false});

  final List<Widget> children;
  final bool voidHeader;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
    );
  }
}

class OracleSection extends StatelessWidget {
  const OracleSection({
    super.key,
    required this.label,
    required this.title,
    required this.child,
    this.voidSection = false,
  });

  final String label;
  final String title;
  final Widget child;
  final bool voidSection;

  @override
  Widget build(BuildContext context) {
    final foreground = voidSection ? OracleColors.cream : OracleColors.ink;
    return Container(
      color: voidSection ? OracleColors.voidColor : OracleColors.cream,
      padding: const EdgeInsets.symmetric(horizontal: 34, vertical: 48),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1120),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label.toUpperCase(),
                style: GoogleFonts.cinzel(
                  color: voidSection ? OracleColors.gold : OracleColors.rust,
                  fontSize: 10,
                  letterSpacing: 3,
                ),
              ),
              const SizedBox(height: 14),
              Container(height: 0.7, color: voidSection ? OracleColors.goldDim : OracleColors.rule),
              const SizedBox(height: 22),
              Text(
                title,
                style: GoogleFonts.ebGaramond(
                  color: foreground,
                  fontSize: 34,
                  fontStyle: FontStyle.italic,
                  height: 1.15,
                ),
              ),
              const SizedBox(height: 24),
              child,
            ],
          ),
        ),
      ),
    );
  }
}

class ConfigHelpCard extends StatelessWidget {
  const ConfigHelpCard({super.key});

  @override
  Widget build(BuildContext context) {
    return const StatusPanel(
      title: 'Firebase config is missing',
      message: 'The public gallery can render static pages, but live sessions need Firebase web config.',
    );
  }
}

class StatusPanel extends StatelessWidget {
  const StatusPanel({super.key, required this.title, required this.message});

  final String title;
  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: OracleColors.paper,
        border: Border.all(color: OracleColors.rule, width: 0.7),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Text(message, style: Theme.of(context).textTheme.bodyMedium),
        ],
      ),
    );
  }
}

class SymbolNetworkView extends StatelessWidget {
  const SymbolNetworkView({super.key, required this.svgUrl, this.size = 150});

  final String svgUrl;
  final double size;

  @override
  Widget build(BuildContext context) {
    if (svgUrl.isEmpty) {
      return _placeholder();
    }
    return SizedBox(
      width: size,
      height: size,
      child: SvgPicture.network(
        svgUrl,
        fit: BoxFit.contain,
        placeholderBuilder: (_) => const Center(
          child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 1.4)),
        ),
      ),
    );
  }

  Widget _placeholder() {
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        border: Border.all(color: OracleColors.rule),
      ),
      child: Text(
        'MARK',
        style: GoogleFonts.cinzel(color: OracleColors.gold, fontSize: 11, letterSpacing: 2),
      ),
    );
  }
}
