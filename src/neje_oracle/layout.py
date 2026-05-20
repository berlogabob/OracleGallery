from __future__ import annotations

import math
import random

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
    organic_enabled: bool = False,
    organic_cell_size_mm: float = 18.0,
    organic_rotation_ramp: float = 0.0,
    organic_scale_ramp: float = 0.0,
    organic_seed: int = 1007,
) -> list[SheetPlacement]:
    normalized_mode = mode.strip().lower()
    if normalized_mode == "hex":
        placements = build_hex_layout(
            count,
            sheet_width_mm=sheet_width_mm,
            sheet_height_mm=sheet_height_mm,
            margin_mm=margin_mm,
            diameter_mm=diameter_mm,
            gap_mm=gap_mm,
        )
    elif normalized_mode == "grid":
        placements = build_grid_layout(
            count,
            sheet_width_mm=sheet_width_mm,
            sheet_height_mm=sheet_height_mm,
            margin_mm=margin_mm,
            diameter_mm=diameter_mm,
            gap_mm=gap_mm,
        )
    else:
        raise ValueError(f"Unsupported plotter layout mode: {mode}")
    if not organic_enabled:
        return placements
    return apply_organic_layout_modifier(
        placements,
        sheet_width_mm=sheet_width_mm,
        sheet_height_mm=sheet_height_mm,
        margin_mm=margin_mm,
        cell_size_mm=organic_cell_size_mm,
        rotation_ramp=organic_rotation_ramp,
        scale_ramp=organic_scale_ramp,
        seed=organic_seed,
    )


def apply_organic_layout_modifier(
    placements: list[SheetPlacement],
    *,
    sheet_width_mm: float,
    sheet_height_mm: float,
    margin_mm: float,
    cell_size_mm: float,
    rotation_ramp: float,
    scale_ramp: float,
    seed: int,
) -> list[SheetPlacement]:
    if not placements:
        return []

    jitter_limit = max(0.0, cell_size_mm)
    rotation_amount = _clamp(rotation_ramp, 0.0, 1.0)
    scale_amount = _clamp(scale_ramp, 0.0, 1.0)
    result: list[SheetPlacement] = []
    for placement in placements:
        rng = random.Random((int(seed) * 1_000_003 + placement.index * 97_531) & 0xFFFFFFFF)
        radius = placement.diameter_mm / 2.0
        max_jitter = min(jitter_limit, placement.diameter_mm * 0.42)
        x_offset = rng.uniform(-max_jitter, max_jitter)
        y_offset = rng.uniform(-max_jitter * 0.55, max_jitter * 0.55)
        center_x = _clamp(
            placement.center_x_mm + x_offset,
            margin_mm + radius,
            sheet_width_mm - margin_mm - radius,
        )
        center_y = _clamp(
            placement.center_y_mm + y_offset,
            margin_mm + radius,
            sheet_height_mm - margin_mm - radius,
        )
        rotation_deg = rng.uniform(-180.0, 180.0) * rotation_amount
        symbol_scale = max(0.1, 1.0 + rng.uniform(-0.45, 0.35) * scale_amount)
        result.append(
            SheetPlacement(
                index=placement.index,
                center_x_mm=center_x,
                center_y_mm=center_y,
                diameter_mm=placement.diameter_mm,
                rotation_deg=rotation_deg,
                symbol_scale=symbol_scale,
                row_y_mm=placement.center_y_mm,
            )
        )
    return result


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


def group_layout_rows(placements: list[SheetPlacement], *, tolerance_mm: float = 0.001) -> list[list[SheetPlacement]]:
    if not placements:
        return []

    sorted_placements = sorted(placements, key=lambda placement: (_row_key(placement), placement.center_x_mm))
    rows: list[list[SheetPlacement]] = []
    for placement in sorted_placements:
        if not rows or abs(_row_key(rows[-1][0]) - _row_key(placement)) > tolerance_mm:
            rows.append([placement])
        else:
            rows[-1].append(placement)
    return [sorted(row, key=lambda placement: placement.center_x_mm) for row in rows]


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
            rotation_deg=placement.rotation_deg,
            symbol_scale=placement.symbol_scale,
            row_y_mm=placement.row_y_mm + shift_y if placement.row_y_mm is not None else None,
        )
        for placement in placements
    ]


def _row_key(placement: SheetPlacement) -> float:
    return placement.row_y_mm if placement.row_y_mm is not None else placement.center_y_mm


def _clamp(value: float, lower: float, upper: float) -> float:
    if lower > upper:
        return (lower + upper) / 2.0
    return max(lower, min(upper, value))
