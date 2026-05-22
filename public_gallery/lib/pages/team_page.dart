import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme/oracle_theme.dart';
import '../widgets/oracle_primitives.dart';

class TeamPage extends StatelessWidget {
  const TeamPage({super.key});

  static const _members = [
    _TeamMember(
      name: 'Andrey Berloga',
      role: 'System, plotter, and publication pipeline',
      bio:
          'Built the local operator stack, Firebase publication flow, plotter controls, and public gallery integration for the exhibition.',
    ),
    _TeamMember(
      name: 'Dmitrii',
      role: 'Documentation and installation media',
      bio:
          'Developed the video and exhibition documentation material that explains how the Oracle moves from voice to mark.',
    ),
    _TeamMember(
      name: 'Oracle Team',
      role: 'Interaction, narrative, and installation support',
      bio:
          'Shaped the visitor experience, mark language, and public narrative around the shared cloth and printed receipts.',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return OraclePage(
      children: [
        OracleSection(
          label: 'Team',
          title: 'The people behind the oracle.',
          child: LayoutBuilder(
            builder: (context, constraints) {
              final columns = constraints.maxWidth > 860 ? 3 : 1;
              return GridView.builder(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: _members.length,
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: columns,
                  mainAxisSpacing: 16,
                  crossAxisSpacing: 16,
                  childAspectRatio: columns == 1 ? 2.8 : 0.82,
                ),
                itemBuilder: (context, index) =>
                    _TeamCard(member: _members[index]),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _TeamCard extends StatelessWidget {
  const _TeamCard({required this.member});

  final _TeamMember member;

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
          Container(
            height: 120,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: OracleColors.cream,
              border: Border.all(color: OracleColors.rule, width: 0.7),
            ),
            child: Text(
              'ORACLE',
              style: GoogleFonts.cinzelDecorative(
                color: OracleColors.goldDim,
                fontSize: 16,
                letterSpacing: 4,
              ),
            ),
          ),
          const SizedBox(height: 18),
          Text(
            member.name.toUpperCase(),
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 6),
          Text(
            member.role,
            style: GoogleFonts.ebGaramond(
              color: OracleColors.rust,
              fontSize: 16,
              fontStyle: FontStyle.italic,
            ),
          ),
          const SizedBox(height: 12),
          Text(member.bio, style: Theme.of(context).textTheme.bodyMedium),
        ],
      ),
    );
  }
}

class _TeamMember {
  const _TeamMember({
    required this.name,
    required this.role,
    required this.bio,
  });

  final String name;
  final String role;
  final String bio;
}
