from evagg.driver_app.geo import haversine_km


def test_same_point_has_zero_distance():
    assert haversine_km((25.2, 55.3), (25.2, 55.3)) == 0.0


def test_known_distance_between_two_cities_is_approximately_correct():
    dubai = (25.2048, 55.2708)
    abu_dhabi = (24.4539, 54.3773)

    distance = haversine_km(dubai, abu_dhabi)

    assert 110 < distance < 140
