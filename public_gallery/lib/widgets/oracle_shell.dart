import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme/oracle_theme.dart';

class OracleShell extends StatelessWidget {
  const OracleShell({
    super.key,
    required this.currentPath,
    required this.child,
  });

  final String currentPath;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: OracleColors.cream,
      body: Column(
        children: [
          _OracleNav(currentPath: currentPath),
          Expanded(child: child),
        ],
      ),
    );
  }
}

class _OracleNav extends StatelessWidget {
  const _OracleNav({required this.currentPath});

  final String currentPath;

  @override
  Widget build(BuildContext context) {
    final links = <_NavLink>[
      const _NavLink('Home', '/'),
      const _NavLink('The Cloth', '/cloth'),
      const _NavLink('The Marks', '/marks'),
      const _NavLink('About', '/about'),
      const _NavLink('Team', '/team'),
    ];
    return Container(
      constraints: const BoxConstraints(minHeight: 72),
      padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 12),
      decoration: const BoxDecoration(
        color: OracleColors.cream,
        border: Border(
          bottom: BorderSide(color: OracleColors.rule, width: 0.7),
        ),
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final compact = constraints.maxWidth < 560;
          final logo = InkWell(
            onTap: () => context.go('/'),
            child: Text(
              'ORACLE',
              style: GoogleFonts.cinzelDecorative(
                color: OracleColors.ink,
                fontSize: compact ? 15 : 18,
                letterSpacing: compact ? 3 : 5,
              ),
            ),
          );
          final nav = Wrap(
            alignment: compact ? WrapAlignment.start : WrapAlignment.end,
            spacing: compact ? 14 : 24,
            runSpacing: 6,
            children: links.map((link) {
              final active = link.path == '/'
                  ? currentPath == '/'
                  : currentPath.startsWith(link.path);
              return InkWell(
                onTap: () => context.go(link.path),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Text(
                    link.label.toUpperCase(),
                    style: GoogleFonts.cinzel(
                      color: active ? OracleColors.rust : OracleColors.inkMuted,
                      fontSize: compact ? 8 : 10,
                      letterSpacing: compact ? 1.6 : 2.4,
                      decoration: active
                          ? TextDecoration.underline
                          : TextDecoration.none,
                      decorationColor: OracleColors.rust,
                    ),
                  ),
                ),
              );
            }).toList(),
          );
          if (compact) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [logo, const SizedBox(height: 8), nav],
            );
          }
          return Row(
            children: [
              logo,
              const Spacer(),
              Flexible(child: nav),
            ],
          );
        },
      ),
    );
  }
}

class _NavLink {
  const _NavLink(this.label, this.path);

  final String label;
  final String path;
}
