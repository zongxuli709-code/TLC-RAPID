"""Safety checks shared by calibration and release tests."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class QuadraticDomain:
    """Geometry of a quadratic calibration over its validated concentration range."""

    vertex: float | None
    vertex_in_range: bool
    concentration_min: float
    concentration_max: float


def inspect_quadratic_domain(a: float, b: float, concentration_min: float,
                             concentration_max: float, *, tolerance: float = 1e-12) -> QuadraticDomain:
    """Return whether a quadratic changes direction inside the standard range."""
    low, high = sorted((float(concentration_min), float(concentration_max)))
    if not all(math.isfinite(value) for value in (a, b, low, high)) or abs(a) <= tolerance:
        return QuadraticDomain(None, False, low, high)

    vertex = -float(b) / (2.0 * float(a))
    scale = max(1.0, abs(low), abs(high))
    margin = tolerance * scale
    return QuadraticDomain(vertex, low + margin < vertex < high - margin, low, high)


def require_unambiguous_quadratic(domain: QuadraticDomain) -> None:
    """Reject inversion when two concentration roots may exist in the standard range."""
    if domain.vertex_in_range:
        raise ValueError(
            "Quadratic calibration is non-monotonic within the standard concentration range "
            f"({domain.concentration_min:g}-{domain.concentration_max:g}; vertex={domain.vertex:g}). "
            "Select linear regression or restrict the validated standards to one side of the vertex."
        )
