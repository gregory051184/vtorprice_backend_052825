from common.utils import str2bool
from rest_framework import filters


class FavoriteFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        is_favorite = str2bool(
            request.query_params.get("is_favorite", "false")
        )

        user = request.user

        if is_favorite:
            if user.is_anonymous:
                queryset = queryset.none()
            else:
                queryset = queryset.filter(is_favorite=True)

        return queryset
