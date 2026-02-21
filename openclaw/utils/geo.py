"""Geo utility helpers. Spatial ops should use PostGIS — this is for formatting only."""


def truncate_wkt(wkt: str, max_len: int = 80) -> str:
    """Truncate WKT for safe logging (never log full geometries)."""
    if not wkt or len(wkt) <= max_len:
        return wkt or ""
    return wkt[:max_len] + "..."


def sq_ft_to_acres(sq_ft: int | float) -> float:
    """Convert square feet to acres."""
    return sq_ft / 43560.0
