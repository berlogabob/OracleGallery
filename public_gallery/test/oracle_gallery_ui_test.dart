import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:public_gallery/app.dart';
import 'package:public_gallery/pages/marks_page.dart';
import 'package:public_gallery/theme/oracle_theme.dart';

void main() {
  testWidgets('mobile navigation keeps all public links visible', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const OracleGalleryApp(firebaseReady: false));
    await tester.pumpAndSettle();

    expect(find.text('HOME'), findsOneWidget);
    expect(find.text('THE CLOTH'), findsOneWidget);
    expect(find.text('THE MARKS'), findsOneWidget);
    expect(find.text('ABOUT'), findsOneWidget);
    expect(find.text('TEAM'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('home lookup routes visitors toward cloth highlight', (
    tester,
  ) async {
    await tester.pumpWidget(const OracleGalleryApp(firebaseReady: false));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.byType(TextField).first);
    await tester.enterText(find.byType(TextField).first, '20260428_183129');
    await tester.ensureVisible(find.widgetWithText(FilledButton, 'Find'));
    await tester.tap(find.widgetWithText(FilledButton, 'Find'));
    await tester.pumpAndSettle();

    expect(find.text('Firebase config is missing'), findsOneWidget);
  });

  testWidgets('marks page renders high contrast svg mark cards', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: OracleTheme.light(),
        home: const Scaffold(body: MarksPage()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(SvgPicture), findsWidgets);
    expect(find.text('THE KIND SOUL'), findsOneWidget);
    expect(find.textContaining('The oracle heard'), findsWidgets);
  });
}
