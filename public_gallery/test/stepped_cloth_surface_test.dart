import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:public_gallery/models/session_data.dart';
import 'package:public_gallery/theme/oracle_theme.dart';
import 'package:public_gallery/widgets/stepped_cloth_surface.dart';

void main() {
  testWidgets('stepped cloth overview does not render per-cell SVG widgets', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: OracleTheme.light(),
        home: Scaffold(
          body: SteppedClothSurface(
            sessions: List.generate(6, _fakeSession),
            highlightSessionId: 'session_002',
          ),
        ),
      ),
    );

    expect(find.byType(CustomPaint), findsWidgets);
    expect(find.byType(SvgPicture), findsNothing);
    expect(find.byTooltip('Mark 2'), findsOneWidget);
  });
}

SessionData _fakeSession(int index) {
  return SessionData(
    sessionId: 'session_${index.toString().padLeft(3, '0')}',
    createdAt: DateTime(2026, 5, 19, 12, index),
    status: 'published',
    plotStatus: 'done',
    markName: 'Mark $index',
    oracleText: 'The oracle has spoken.',
    themes: const <String>['test'],
    measures: const <String, double>{},
    svgUrl: 'https://example.com/mark_$index.svg',
    receiptUrl: '',
    qrUrl: '',
    sessionUrl: '',
    qrImageUrl: '',
    tarotUrl: '',
    origin: 'real',
    tags: const <String>[],
    visibleInLibrary: true,
  );
}
