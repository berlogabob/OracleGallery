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
  final coordinates = _spiralCoordinates(capacity);
  final minX = coordinates.map((point) => point.x).reduce(math.min);
  final minY = coordinates.map((point) => point.y).reduce(math.min);

  return ClothGridLayout(
    side: side,
    filledCount: normalizedCount,
    placements: [
      for (var index = 0; index < coordinates.length; index++)
        ClothGridPlacement(
          index: index,
          row: coordinates[index].y - minY,
          column: coordinates[index].x - minX,
        ),
    ],
  );
}

List<math.Point<int>> _spiralCoordinates(int count) {
  final coordinates = <math.Point<int>>[const math.Point<int>(0, 0)];
  for (var radius = 1; coordinates.length < count; radius++) {
    for (var y = 1 - radius; y <= radius && coordinates.length < count; y++) {
      coordinates.add(math.Point<int>(radius, y));
    }
    for (var x = radius - 1; x >= -radius && coordinates.length < count; x--) {
      coordinates.add(math.Point<int>(x, radius));
    }
    for (var y = radius - 1; y >= -radius && coordinates.length < count; y--) {
      coordinates.add(math.Point<int>(-radius, y));
    }
    for (var x = -radius + 1; x <= radius && coordinates.length < count; x++) {
      coordinates.add(math.Point<int>(x, -radius));
    }
  }
  return coordinates;
}
