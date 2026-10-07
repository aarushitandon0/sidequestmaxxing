"""Geo helpers: haversine distance and geohash-5 neighbourhoods (MASTERSPEC §3.1, §16)."""

import math

import pygeohash as pgh

EARTH_RADIUS_M = 6_371_008.8
CELL_PRECISION = 5  # ~4.9 km x 4.9 km at the equator


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def cell5(lat: float, lng: float) -> str:
    return str(pgh.encode(lat, lng, precision=CELL_PRECISION))


def neighbours(cell: str) -> list[str]:
    """The 8 cells around `cell` (fewer at the poles)."""
    out: list[str] = []
    for vertical in ("top", "bottom", None):
        try:
            row = pgh.get_adjacent(cell, vertical) if vertical else cell
        except ValueError:
            continue  # beyond a pole
        out.append(row) if vertical else None
        for horizontal in ("left", "right"):
            out.append(pgh.get_adjacent(row, horizontal))
    return out


def cells_around(lat: float, lng: float) -> list[str]:
    """Centre cell first, then its neighbours; deduplicated, order stable."""
    centre = cell5(lat, lng)
    seen: dict[str, None] = {centre: None}
    for cell in neighbours(centre):
        seen.setdefault(cell, None)
    return list(seen)
