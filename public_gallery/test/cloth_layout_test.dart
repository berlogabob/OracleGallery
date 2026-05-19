import 'package:flutter_test/flutter_test.dart';
import 'package:public_gallery/widgets/cloth_layout.dart';

void main() {
  test('cloth layout advances in square capacities', () {
    final expectations = <int, int>{
      0: 0,
      1: 1,
      3: 1,
      4: 2,
      5: 2,
      8: 2,
      9: 3,
      10: 3,
      16: 4,
      159: 12,
      168: 12,
      169: 13,
    };

    for (final entry in expectations.entries) {
      final layout = buildClothGridLayout(entry.key);
      expect(layout.side, entry.value, reason: 'count ${entry.key}');
      expect(
        layout.capacity,
        entry.value * entry.value,
        reason: 'count ${entry.key}',
      );
      expect(
        layout.placements.length,
        layout.capacity,
        reason: 'count ${entry.key}',
      );
      expect(
        layout.hiddenRemainder,
        entry.key - layout.capacity,
        reason: 'count ${entry.key}',
      );
    }
  });

  test('cloth fills row by row inside the current square', () {
    final nine = buildClothGridLayout(9);
    expect(
      nine.placements.map((placement) => (placement.row, placement.column)),
      [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2)],
    );
  });

  test(
    'partial squares hold the previous full square until enough symbols arrive',
    () {
      final five = buildClothGridLayout(5);
      expect(five.side, 2);
      expect(five.capacity, 4);
      expect(five.hiddenRemainder, 1);
      expect(five.placements.map((placement) => placement.index), [0, 1, 2, 3]);
    },
  );
}
