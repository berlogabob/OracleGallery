import 'dart:math' as math;

class ClothGridLayout {
  const ClothGridLayout({
    required this.side,
    required this.placements,
    required this.sourceCount,
  });

  final int side;
  final List<ClothGridPlacement> placements;
  final int sourceCount;

  int get capacity => side * side;

  int get hiddenRemainder => sourceCount - capacity;
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
  final side = normalizedCount == 0 ? 0 : math.sqrt(normalizedCount).floor();
  if (side == 0) {
    return const ClothGridLayout(
      side: 0,
      placements: <ClothGridPlacement>[],
      sourceCount: 0,
    );
  }

  final capacity = side * side;
  return ClothGridLayout(
    side: side,
    sourceCount: normalizedCount,
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
