from __future__ import annotations

import math

from .models import SheetPlacement


def build_hex_layout(
    count: int,
    *,
    sheet_width_mm: float,
    sheet_height_mm: float,
    margin_mm: float,
    diameter_mm: float,
) -> list[SheetPlacement]:
    if count <= 0:
        return []

    radius = diameter_mm / 2.0
    horizontal_step = diameter_mm
    vertical_step = math.sqrt(3.0) * radius
    placements: list[SheetPlacement] = []

    row = 0
    while len(placements) < count:
        center_y = margin_mm + radius + (row * vertical_step)
        if center_y + radius > sheet_height_mm - margin_mm:
            break
        offset = radius if row % 2 else 0.0
        col = 0
        while len(placements) < count:
            center_x = margin_mm + radius + offset + (col * horizontal_step)
            if center_x + radius > sheet_width_mm - margin_mm:
                break
            placements.append(
                SheetPlacement(
                    index=len(placements),
                    center_x_mm=center_x,
                    center_y_mm=center_y,
                    diameter_mm=diameter_mm,
                )
            )
            col += 1
        row += 1
    return placements


def build_grid_layout(
    count: int,
    *,
    sheet_width_mm: float,
    sheet_height_mm: float,
    margin_mm: float,
    diameter_mm: float,
) -> list[SheetPlacement]:
    if count <= 0:
        return []

    radius = diameter_mm / 2.0
    placements: list[SheetPlacement] = []
    row = 0
    while len(placements) < count:
        center_y = margin_mm + radius + (row * diameter_mm)
        if center_y + radius > sheet_height_mm - margin_mm:
            break
        col = 0
        while len(placements) < count:
            center_x = margin_mm + radius + (col * diameter_mm)
            if center_x + radius > sheet_width_mm - margin_mm:
                break
            placements.append(
                SheetPlacement(
                    index=len(placements),
                    center_x_mm=center_x,
                    center_y_mm=center_y,
                    diameter_mm=diameter_mm,
                )
            )
            col += 1
        row += 1
    return placements


def build_sheet_layout(
    count: int,
    *,
    mode: str,
    sheet_width_mm: float,
    sheet_height_mm: float,
    margin_mm: float,
    diameter_mm: float,
) -> list[SheetPlacement]:
    normalized_mode = mode.strip().lower()
    if normalized_mode == "hex":
        return build_hex_layout(
            count,
            sheet_width_mm=sheet_width_mm,
            sheet_height_mm=sheet_height_mm,
            margin_mm=margin_mm,
            diameter_mm=diameter_mm,
        )
    if normalized_mode == "grid":
        return build_grid_layout(
            count,
            sheet_width_mm=sheet_width_mm,
            sheet_height_mm=sheet_height_mm,
            margin_mm=margin_mm,
            diameter_mm=diameter_mm,
        )
    raise ValueError(f"Unsupported plotter layout mode: {mode}")


def calculate_layout_capacity(
    *,
    mode: str,
    sheet_width_mm: float,
    sheet_height_mm: float,
    margin_mm: float,
    diameter_mm: float,
) -> int:
    return len(
        build_sheet_layout(
            10_000,
            mode=mode,
            sheet_width_mm=sheet_width_mm,
            sheet_height_mm=sheet_height_mm,
            margin_mm=margin_mm,
            diameter_mm=diameter_mm,
        )
    )
