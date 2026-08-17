from geoalchemy2.elements import WKTElement


def make_point(latitude: float, longitude: float) -> WKTElement:
    """Build a PostGIS geography point (SRID 4326) from lat/lon."""
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)
