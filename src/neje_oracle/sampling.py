from __future__ import annotations


def compute_effective_sample_step(
    *,
    sample_step_mm: float,
    cell_diameter_mm: float,
    sample_reference_cell_mm: float,
    sample_density_exponent: float,
    sample_min_step_mm: float,
    sample_max_step_mm: float,
) -> float:
    """Return the G-code sampling step adjusted for the current cell size."""
    ratio = sample_reference_cell_mm / max(cell_diameter_mm, 1e-9)
    effective = sample_step_mm * (ratio ** sample_density_exponent)
    return max(sample_min_step_mm, min(sample_max_step_mm, effective))
