import pytest

from app.services.geo import cell5, cells_around, haversine_m, neighbours


@pytest.mark.parametrize(
    ("a", "b", "expected_m", "tol_m"),
    [
        ((18.520, 73.856), (18.520, 73.856), 0, 0.001),
        ((0.0, 0.0), (0.0, 1.0), 111_195, 50),
        ((0.0, 0.0), (1.0, 0.0), 111_195, 50),
        ((51.5007, -0.1246), (40.6892, -74.0445), 5_574_840, 2_000),  # Big Ben → Liberty
        ((18.5204, 73.8567), (18.5304, 73.8567), 1_112, 2),
        ((-33.8568, 151.2153), (-33.8568, 151.2153 + 0.01), 925, 2),
        ((0.0, 179.9995), (0.0, -179.9995), 111, 1),  # across the antimeridian
    ],
)
def test_haversine(
    a: tuple[float, float], b: tuple[float, float], expected_m: float, tol_m: float
) -> None:
    assert haversine_m(*a, *b) == pytest.approx(expected_m, abs=tol_m)


def test_haversine_symmetric() -> None:
    assert haversine_m(18.5, 73.8, 18.6, 73.9) == pytest.approx(haversine_m(18.6, 73.9, 18.5, 73.8))


def test_cell5_is_precision_5_and_contains_point() -> None:
    import pygeohash as pgh

    cell = cell5(18.5204, 73.8567)
    assert len(cell) == 5
    centre = pgh.decode_exactly(cell)
    assert abs(centre.latitude - 18.5204) <= centre.latitude_error
    assert abs(centre.longitude - 73.8567) <= centre.longitude_error


def test_neighbours_are_eight_distinct_adjacent_cells() -> None:
    import pygeohash as pgh

    centre = cell5(18.5204, 73.8567)
    ns = neighbours(centre)
    assert len(ns) == 8
    assert len(set(ns)) == 8
    assert centre not in ns
    c = pgh.decode_exactly(centre)
    offsets = set()
    for n in ns:
        d = pgh.decode_exactly(n)
        offsets.add(
            (
                round((d.latitude - c.latitude) / (2 * c.latitude_error)),
                round((d.longitude - c.longitude) / (2 * c.longitude_error)),
            )
        )
    assert offsets == {(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)} - {(0, 0)}


def test_cells_around_centre_first_and_covers_nearby_point() -> None:
    cells = cells_around(18.5204, 73.8567)
    assert cells[0] == cell5(18.5204, 73.8567)
    assert len(cells) == 9
    # A point ~3 km away must fall into the 3x3 block.
    assert cell5(18.5474, 73.8567) in cells


def test_cells_around_near_pole_does_not_crash() -> None:
    cells = cells_around(89.99, 0.0)
    assert 1 <= len(cells) <= 9
