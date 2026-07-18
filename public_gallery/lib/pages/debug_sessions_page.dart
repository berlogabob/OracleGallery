import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../models/session_data.dart';
import '../services/session_repository.dart';
import '../theme/oracle_theme.dart';
import '../widgets/oracle_primitives.dart';

class DebugSessionsPage extends StatelessWidget {
  const DebugSessionsPage({super.key, required this.firebaseReady});

  final bool firebaseReady;

  @override
  Widget build(BuildContext context) {
    return OraclePage(
      children: [
        OracleSection(
          label: 'Private debug',
          title: 'All Firebase sessions for testing and operator review.',
          child: firebaseReady
              ? const _DebugSessionStream()
              : const ConfigHelpCard(),
        ),
      ],
    );
  }
}

const _debugOrigins = <String>[
  'real_macmini',
  'test_macbook',
  'test_macmini',
  'filler_macbook',
  'unknown',
];

class _DebugSessionStream extends StatefulWidget {
  const _DebugSessionStream();

  @override
  State<_DebugSessionStream> createState() => _DebugSessionStreamState();
}

class _DebugSessionStreamState extends State<_DebugSessionStream> {
  final Set<String> _selectedOrigins = {..._debugOrigins};
  final Set<String> _selectedTags = {};
  final Stream<List<SessionData>> _sessions = SessionRepository()
      .watchAllSessions();

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<List<SessionData>>(
      stream: _sessions,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return StatusPanel(
            title: 'Could not load sessions',
            message: snapshot.error.toString(),
          );
        }
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(28),
              child: CircularProgressIndicator(),
            ),
          );
        }
        final sessions = snapshot.data ?? const <SessionData>[];
        final allTags =
            sessions
                .expand((session) => session.tags)
                .map((tag) => tag.toLowerCase())
                .toSet()
                .toList()
              ..sort();
        final filtered = sessions.where(_matchesFilters).toList();
        if (sessions.isEmpty) {
          return const StatusPanel(
            title: 'No sessions found',
            message: 'Firestore returned no session documents.',
          );
        }

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'TOTAL SESSIONS · ${sessions.length.toString().padLeft(3, '0')} / SHOWN · ${filtered.length.toString().padLeft(3, '0')}',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 18),
            _DebugFilters(
              origins: _debugOrigins,
              selectedOrigins: _selectedOrigins,
              tags: allTags,
              selectedTags: _selectedTags,
              onOriginChanged: _toggleOrigin,
              onTagChanged: _toggleTag,
            ),
            const SizedBox(height: 18),
            LayoutBuilder(
              builder: (context, constraints) {
                final crossAxisCount = constraints.maxWidth > 1080
                    ? 4
                    : constraints.maxWidth > 760
                    ? 3
                    : 2;
                return GridView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: filtered.length,
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: crossAxisCount,
                    mainAxisSpacing: 14,
                    crossAxisSpacing: 14,
                    childAspectRatio: 0.66,
                  ),
                  itemBuilder: (context, index) =>
                      _DebugSessionCard(session: filtered[index]),
                );
              },
            ),
          ],
        );
      },
    );
  }

  bool _matchesFilters(SessionData session) {
    final origin = session.origin.isEmpty ? 'unknown' : session.origin;
    if (!_selectedOrigins.contains(origin)) {
      return false;
    }
    if (_selectedTags.isEmpty) {
      return true;
    }
    final tags = session.tags.map((tag) => tag.toLowerCase()).toSet();
    return _selectedTags.every(tags.contains);
  }

  void _toggleOrigin(String origin, bool selected) {
    setState(() {
      if (selected) {
        _selectedOrigins.add(origin);
      } else {
        _selectedOrigins.remove(origin);
      }
    });
  }

  void _toggleTag(String tag, bool selected) {
    setState(() {
      if (selected) {
        _selectedTags.add(tag.toLowerCase());
      } else {
        _selectedTags.remove(tag.toLowerCase());
      }
    });
  }
}

class _DebugFilters extends StatelessWidget {
  const _DebugFilters({
    required this.origins,
    required this.selectedOrigins,
    required this.tags,
    required this.selectedTags,
    required this.onOriginChanged,
    required this.onTagChanged,
  });

  final List<String> origins;
  final Set<String> selectedOrigins;
  final List<String> tags;
  final Set<String> selectedTags;
  final void Function(String origin, bool selected) onOriginChanged;
  final void Function(String tag, bool selected) onTagChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: OracleColors.paper,
        border: Border.all(color: OracleColors.rule, width: 0.7),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('DEBUG FILTERS', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final origin in origins)
                FilterChip(
                  label: Text(origin.replaceAll('_', ' ').toUpperCase()),
                  selected: selectedOrigins.contains(origin),
                  onSelected: (selected) => onOriginChanged(origin, selected),
                ),
            ],
          ),
          if (tags.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final tag in tags)
                  FilterChip(
                    label: Text('#$tag'),
                    selected: selectedTags.contains(tag),
                    onSelected: (selected) => onTagChanged(tag, selected),
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _DebugSessionCard extends StatelessWidget {
  const _DebugSessionCard({required this.session});

  final SessionData session;

  @override
  Widget build(BuildContext context) {
    final hidden = !session.isPublicInLibrary;
    return InkWell(
      onTap: () => context.go('/session/${session.sessionId}'),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: hidden ? OracleColors.cream : OracleColors.paper,
          border: Border.all(
            color: hidden ? OracleColors.rust : OracleColors.rule,
            width: 0.8,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(child: SymbolNetworkView(svgUrl: session.svgUrl, size: 116)),
            const SizedBox(height: 12),
            Text(
              session.markName.isEmpty
                  ? 'UNNAMED MARK'
                  : session.markName.toUpperCase(),
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: GoogleFonts.cinzel(
                color: OracleColors.ink,
                fontSize: 12,
                letterSpacing: 1.4,
              ),
            ),
            const SizedBox(height: 8),
            SelectableText(
              session.sessionId,
              textAlign: TextAlign.center,
              style: GoogleFonts.cinzel(
                color: OracleColors.goldDim,
                fontSize: 10,
                letterSpacing: 1.4,
              ),
            ),
            const SizedBox(height: 10),
            Wrap(
              alignment: WrapAlignment.center,
              spacing: 6,
              runSpacing: 6,
              children: [
                _Pill(session.status),
                _Pill(session.plotStatus),
                _Pill(session.origin.isEmpty ? 'unknown' : session.origin),
                if (hidden) const _Pill('hidden'),
              ],
            ),
            const SizedBox(height: 10),
            Expanded(
              child: Text(
                session.oracleText,
                maxLines: 5,
                overflow: TextOverflow.fade,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        border: Border.all(color: OracleColors.rule, width: 0.7),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label.toUpperCase(),
        style: GoogleFonts.cinzel(
          color: OracleColors.inkMuted,
          fontSize: 8,
          letterSpacing: 1.2,
        ),
      ),
    );
  }
}
