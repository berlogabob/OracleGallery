import 'package:flutter_test/flutter_test.dart';
import 'package:public_gallery/widgets/cloth_layout.dart';

void main() {
  test('cloth layout advances in square capacities', () {
    final expectations = <int, int>{0: 0, 1: 1, 4: 2, 5: 3, 9: 3, 10: 4, 16: 4};

    for (final entry in expectations.entries) {
      final layout = buildClothGridLayout(entry.key);
      expect(layout.side, entry.value, reason: 'count ${entry.key}');
      expect(
        layout.capacity,
        entry.value * entry.value,
        reason: 'count ${entry.key}',
      );
      expect(
        layout.filledPlacements.length,
        entry.key,
        reason: 'count ${entry.key}',
      );
      expect(
        layout.futurePlacements.length,
        layout.capacity - entry.key,
        reason: 'count ${entry.key}',
      );
    }
  });

  test(
    'oldest placement sits at the square center when there is one center cell',
    () {
      final one = buildClothGridLayout(1);
      expect(one.placements.first.row, 0);
      expect(one.placements.first.column, 0);

      final threeByThree = buildClothGridLayout(5);
      expect(threeByThree.placements.first.row, 1);
      expect(threeByThree.placements.first.column, 1);
    },
  );

  test('partial squares expose faint future cells', () {
    final five = buildClothGridLayout(5);
    expect(five.side, 3);
    expect(five.filledPlacements.map((placement) => placement.index), [
      0,
      1,
      2,
      3,
      4,
    ]);
    expect(five.futurePlacements.map((placement) => placement.index), [
      5,
      6,
      7,
      8,
    ]);
  });
}
