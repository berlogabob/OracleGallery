import 'package:flutter_test/flutter_test.dart';
import 'package:public_gallery/widgets/cloth_layout.dart';

void main() {
  test('grid side is the smallest square that fits every mark', () {
    final expectations = <int, int>{
      0: 0,
      1: 1,
      3: 2,
      4: 2,
      5: 3,
      8: 3,
      9: 3,
      10: 4,
      16: 4,
      159: 13,
      168: 13,
      169: 13,
    };

    for (final entry in expectations.entries) {
      final layout = buildClothGridLayout(entry.key);
      expect(layout.side, entry.value, reason: 'count ${entry.key}');
      // No mark is ever dropped: every source count is fully placed.
      expect(
        layout.placements.length,
        entry.key,
        reason: 'count ${entry.key}',
      );
      expect(
        layout.placements.map((p) => p.index),
        List.generate(entry.key, (i) => i),
        reason: 'count ${entry.key}',
      );
    }
  });

  test('cloth fills row by row, last row may be partial', () {
    final five = buildClothGridLayout(5);
    expect(five.side, 3);
    expect(
      five.placements.map((placement) => (placement.row, placement.column)),
      [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1)],
    );
  });
}
