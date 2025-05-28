from typing import List, Tuple

from rest_framework.exceptions import ValidationError
from shapely import Polygon, Point


def parse_coordinates(raw_coordinates: List) -> List[List[float]]:
    """
    Makes from List of strings to a list of list of floats
    e.g: ['20,20', '20,40', '40,40', '20,40'] -> [[20.0, 20.0], [20.0, 40.0], [40.0, 40.0], [20.0, 40.0]]
    """
    return [list(map(float, i.split(","))) for i in raw_coordinates]


def get_latitude_borders(
    list_of_coordinates: List[List[float]],
) -> Tuple[float, float]:
    """
    Gets min and max value of latitude from List of points
    """

    min_latitude, max_latitude = min(i[0] for i in list_of_coordinates), max(
        i[0] for i in list_of_coordinates
    )
    return min_latitude, max_latitude


def get_longitude_borders(
    list_of_coordinates: List[List[float]],
) -> Tuple[float, float]:
    """
    Gets min and max value of longitude from List of points
    """
    min_longitude, max_longitude = min(i[1] for i in list_of_coordinates), max(
        i[1] for i in list_of_coordinates
    )
    return min_longitude, max_longitude


def validate_coordinates(coordinates: List[List[float]]):
    """
    Checks is List of coordinates can be a polygon.
    Firstly, checks if there were given at least 3 coordinates.
    Secondly, checks that all coordinate list consist from exactly 2 points.

    If at least one check were not passed -> raises ValidationError
    """
    if len(coordinates) < 3:
        raise ValidationError(
            f"Необходимо минимум 3 точки, предоставлено: {len(coordinates)}"
        )

    if any(map(lambda x: len(x) != 2, coordinates)):
        raise ValidationError("Некорректный формат ввода точек.")


def filter_qs_by_coordinates(qs, raw_coordinates):
    """
    Filters given queryset by given coordinates.
    Returns objects that satisfies given borders.
    """
    list_of_coordinates = parse_coordinates(raw_coordinates)
    validate_coordinates(list_of_coordinates)
    # Finding min and max for each coordinate
    min_latitude, max_latitude = get_latitude_borders(list_of_coordinates)
    min_longitude, max_longitude = get_longitude_borders(list_of_coordinates)
    # Creating polygon from coordinates
    polygon = Polygon(list_of_coordinates)
    # Filtering firstly by extremum values
    qs = qs.filter(
        latitude__gte=min_latitude,
        latitude__lte=max_latitude,
        longitude__gte=min_longitude,
        longitude__lte=max_longitude,
    )
    # Secondly, check if objects in given polygon
    filtered_ids = list(
        map(
            lambda filtered_recyclable: filtered_recyclable.pk,
            filter(
                lambda recyclable: polygon.contains(
                    Point(
                        float(recyclable.latitude),
                        float(recyclable.longitude),
                    )
                ),
                qs,
            ),
        )
    )
    qs = qs.filter(id__in=filtered_ids)
    return qs
