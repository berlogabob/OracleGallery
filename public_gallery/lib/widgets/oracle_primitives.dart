import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme/oracle_theme.dart';

class OraclePage extends StatelessWidget {
  const OraclePage({
    super.key,
    required this.children,
    this.voidHeader = false,
  });

  final List<Widget> children;
  final bool voidHeader;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: children,
      ),
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
    final textTheme = Theme.of(context).textTheme;
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
                style: textTheme.titleMedium?.copyWith(
                  color: voidSection ? OracleColors.gold : OracleColors.rust,
                  fontSize: 10,
                  letterSpacing: 3,
                ),
              ),
              const SizedBox(height: 14),
              Container(
                height: 0.7,
                color: voidSection ? OracleColors.goldDim : OracleColors.rule,
              ),
              const SizedBox(height: 22),
              Text(
                title,
                style: textTheme.bodyLarge?.copyWith(
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

/// Shared paper-card decoration: a flat color fill with a thin rule border.
///
/// Use [OracleCard] for the default paper/rule treatment used across
/// content cards, and [OracleCard.accent] for the void-background,
/// gold-family border treatment used on the two "highlighted" surfaces
/// (the cloth's highlighted session panel and the home page cloth
/// preview).
class OracleCard extends StatelessWidget {
  const OracleCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(22),
    this.color = OracleColors.paper,
    this.borderColor = OracleColors.rule,
    this.borderWidth = 0.7,
    this.width,
    this.height,
    this.alignment,
  });

  const OracleCard.accent({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(18),
    this.color = OracleColors.voidColor,
    this.borderColor = OracleColors.gold,
    this.borderWidth = 0.8,
    this.width,
    this.height,
    this.alignment,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color color;
  final Color borderColor;
  final double borderWidth;
  final double? width;
  final double? height;
  final AlignmentGeometry? alignment;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      alignment: alignment,
      padding: padding,
      decoration: BoxDecoration(
        color: color,
        border: Border.all(color: borderColor, width: borderWidth),
      ),
      child: child,
    );
  }
}

class ConfigHelpCard extends StatelessWidget {
  const ConfigHelpCard({super.key});

  @override
  Widget build(BuildContext context) {
    return const StatusPanel(
      title: 'Firebase config is missing',
      message:
          'The public gallery can render static pages, but live sessions need Firebase web config.',
    );
  }
}

class StatusPanel extends StatelessWidget {
  const StatusPanel({super.key, required this.title, required this.message});

  final String title;
  final String message;

  @override
  Widget build(BuildContext context) {
    return OracleCard(
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
      return _placeholder(context);
    }
    return SizedBox(
      width: size,
      height: size,
      child: SvgPicture.network(
        svgUrl,
        fit: BoxFit.contain,
        placeholderBuilder: (_) => const Center(
          child: SizedBox(
            width: 18,
            height: 18,
            child: CircularProgressIndicator(strokeWidth: 1.4),
          ),
        ),
      ),
    );
  }

  Widget _placeholder(BuildContext context) {
    return OracleCard(
      width: size,
      height: size,
      alignment: Alignment.center,
      color: Colors.transparent,
      padding: EdgeInsets.zero,
      child: Text(
        'MARK',
        style: Theme.of(context).textTheme.titleMedium?.copyWith(
          color: OracleColors.gold,
          fontSize: 11,
          letterSpacing: 2,
        ),
      ),
    );
  }
}
