import 'dart:math' as math;

class ClothGridLayout {
  const ClothGridLayout({required this.side, required this.placements});

  final int side;
  final List<ClothGridPlacement> placements;
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

/// Smallest square grid that holds every mark. The last row may be partial so
/// that newly published marks appear immediately instead of waiting for the
/// next perfect square to fill.
ClothGridLayout buildClothGridLayout(int filledCount) {
  final count = math.max(0, filledCount);
  final side = count == 0 ? 0 : math.sqrt(count).ceil();
  return ClothGridLayout(
    side: side,
    placements: [
      for (var index = 0; index < count; index++)
        ClothGridPlacement(
          index: index,
          row: index ~/ side,
          column: index % side,
        ),
    ],
  );
}
