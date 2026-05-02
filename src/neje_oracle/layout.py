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
    gap_mm: float = 0.0,
) -> list[SheetPlacement]:
    if count <= 0:
        return []

    radius = diameter_mm / 2.0
    pitch = max(diameter_mm + gap_mm, diameter_mm)
    horizontal_step = pitch
    vertical_step = math.sqrt(3.0) * pitch / 2.0
    printable_width = max(sheet_width_mm - (margin_mm * 2.0), 0.0)
    even_row_columns = max(int((printable_width + gap_mm) // pitch), 0)
    if even_row_columns <= 0:
        return []
    placements: list[SheetPlacement] = []

    row = 0
    while len(placements) < count:
        center_y = margin_mm + radius + (row * vertical_step)
        if center_y + radius > sheet_height_mm - margin_mm:
            break
        row_columns = even_row_columns if row % 2 == 0 else max(even_row_columns - 1, 0)
        offset = pitch / 2.0 if row % 2 else 0.0
        for col in range(row_columns):
            if len(placements) >= count:
                break
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
        row += 1
    return _center_placements(
        placements,
        sheet_width_mm=sheet_width_mm,
        sheet_height_mm=sheet_height_mm,
        margin_mm=margin_mm,
    )


def build_grid_layout(
    count: int,
    *,
    sheet_width_mm: float,
    sheet_height_mm: float,
    margin_mm: float,
    diameter_mm: float,
    gap_mm: float = 0.0,
) -> list[SheetPlacement]:
    if count <= 0:
        return []

    radius = diameter_mm / 2.0
    pitch = max(diameter_mm + gap_mm, diameter_mm)
    printable_width = max(sheet_width_mm - (margin_mm * 2.0), 0.0)
    columns = max(int((printable_width + gap_mm) // pitch), 0)
    if columns <= 0:
        return []
    placements: list[SheetPlacement] = []
    row = 0
    while len(placements) < count:
        center_y = margin_mm + radius + (row * pitch)
        if center_y + radius > sheet_height_mm - margin_mm:
            break
        for col in range(columns):
            if len(placements) >= count:
                break
            center_x = margin_mm + radius + (col * pitch)
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
        row += 1
    return _center_placements(
        placements,
        sheet_width_mm=sheet_width_mm,
        sheet_height_mm=sheet_height_mm,
        margin_mm=margin_mm,
    )


def build_sheet_layout(
    count: int,
    *,
    mode: str,
    sheet_width_mm: float,
    sheet_height_mm: float,
    margin_mm: float,
    diameter_mm: float,
    gap_mm: float = 0.0,
) -> list[SheetPlacement]:
    normalized_mode = mode.strip().lower()
    if normalized_mode == "hex":
        return build_hex_layout(
            count,
            sheet_width_mm=sheet_width_mm,
            sheet_height_mm=sheet_height_mm,
            margin_mm=margin_mm,
            diameter_mm=diameter_mm,
            gap_mm=gap_mm,
        )
    if normalized_mode == "grid":
        return build_grid_layout(
            count,
            sheet_width_mm=sheet_width_mm,
            sheet_height_mm=sheet_height_mm,
            margin_mm=margin_mm,
            diameter_mm=diameter_mm,
            gap_mm=gap_mm,
        )
    raise ValueError(f"Unsupported plotter layout mode: {mode}")


def calculate_layout_capacity(
    *,
    mode: str,
    sheet_width_mm: float,
    sheet_height_mm: float,
    margin_mm: float,
    diameter_mm: float,
    gap_mm: float = 0.0,
) -> int:
    return len(
        build_sheet_layout(
            10_000,
            mode=mode,
            sheet_width_mm=sheet_width_mm,
            sheet_height_mm=sheet_height_mm,
            margin_mm=margin_mm,
            diameter_mm=diameter_mm,
            gap_mm=gap_mm,
        )
    )


def _center_placements(
    placements: list[SheetPlacement],
    *,
    sheet_width_mm: float,
    sheet_height_mm: float,
    margin_mm: float,
) -> list[SheetPlacement]:
    if not placements:
        return []

    min_x = min(placement.center_x_mm - (placement.diameter_mm / 2.0) for placement in placements)
    max_x = max(placement.center_x_mm + (placement.diameter_mm / 2.0) for placement in placements)
    min_y = min(placement.center_y_mm - (placement.diameter_mm / 2.0) for placement in placements)
    max_y = max(placement.center_y_mm + (placement.diameter_mm / 2.0) for placement in placements)

    printable_center_x = margin_mm + ((sheet_width_mm - (margin_mm * 2.0)) / 2.0)
    printable_center_y = margin_mm + ((sheet_height_mm - (margin_mm * 2.0)) / 2.0)
    used_center_x = (min_x + max_x) / 2.0
    used_center_y = (min_y + max_y) / 2.0
    shift_x = printable_center_x - used_center_x
    shift_y = printable_center_y - used_center_y

    return [
        SheetPlacement(
            index=placement.index,
            center_x_mm=placement.center_x_mm + shift_x,
            center_y_mm=placement.center_y_mm + shift_y,
            diameter_mm=placement.diameter_mm,
        )
        for placement in placements
    ]
