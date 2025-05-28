from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class PageSizePagination(PageNumberPagination):
    """
    Paginator with page number and page size as query params. Both page count and total
    count added to the response Extended PageNumber paginator of DRF.
    """

    page_size_query_param = "size"

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "page_count": self.page.paginator.num_pages,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "example": 123,
                },
                "page_count": {
                    "type": "integer",
                    "example": 123,
                },
                "next": {
                    "type": "string",
                    "nullable": True,
                    "format": "uri",
                    "example": "http://api.example.org/accounts/?{page_query_param}=4&{page_size_query_param}=10".format(
                        page_query_param=self.page_query_param,
                        page_size_query_param=self.page_size_query_param,
                    ),
                },
                "previous": {
                    "type": "string",
                    "nullable": True,
                    "format": "uri",
                    "example": "http://api.example.org/accounts/?{page_query_param}=2&{page_size_query_param}=10".format(
                        page_query_param=self.page_query_param,
                        page_size_query_param=self.page_size_query_param,
                    ),
                },
                "results": schema,
            },
        }
