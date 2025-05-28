from typing import Collection


def validate_logistics_coordinates(coordinates: Collection):
    if any([not x for x in coordinates]):
        raise ValueError("You must specify all coordinates")
    return coordinates
