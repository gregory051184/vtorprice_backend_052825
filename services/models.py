from pydantic import BaseModel


class AddressData(BaseModel):
    address: str
    city: int
    longitude: float
    latitude: float


class DeliveryCost(BaseModel):
    price_per_km: float
    distance: float
    total_price: float

    @classmethod
    def from_coordinates(
        cls, departure_coordinates, delivery_coordinates, price_per_km
    ):
        from geopy.distance import geodesic

        distance = geodesic(departure_coordinates, delivery_coordinates).km
        total_price = distance * price_per_km
        return cls(
            price_per_km=round(price_per_km, 2),
            distance=round(distance, 2),
            total_price=round(total_price, 2),
        )
