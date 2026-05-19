import 'dart:math' as math;

class ClothGridLayout {
  const ClothGridLayout({
    required this.side,
    required this.filledCount,
    required this.placements,
  });

  final int side;
  final int filledCount;
  final List<ClothGridPlacement> placements;

  int get capacity => side * side;

  Iterable<ClothGridPlacement> get filledPlacements =>
      placements.take(filledCount);

  Iterable<ClothGridPlacement> get futurePlacements =>
      placements.skip(filledCount);
}

class ClothGridPlacement {
  const ClothGridPlacement({
    required this.index,
    required this.row,
    required this.column,
  });

  final int index;
  final int row;
  final int column;
}

ClothGridLayout buildClothGridLayout(int filledCount) {
  final normalizedCount = math.max(0, filledCount);
  final side = normalizedCount == 0 ? 0 : math.sqrt(normalizedCount).ceil();
  if (side == 0) {
    return const ClothGridLayout(
      side: 0,
      filledCount: 0,
      placements: <ClothGridPlacement>[],
    );
  }

  final capacity = side * side;
  return ClothGridLayout(
    side: side,
    filledCount: normalizedCount,
    placements: [
      for (var index = 0; index < capacity; index++)
        ClothGridPlacement(
          index: index,
          row: index ~/ side,
          column: index % side,
        ),
    ],
  );
}
