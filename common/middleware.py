from django.conf import settings


class MiddlewareMixin(object):
    def __init__(self, get_response=None):
        self.get_response = get_response
        super(MiddlewareMixin, self).__init__()

    def __call__(self, request):
        response = None
        if hasattr(self, "process_request"):
            response = self.process_request(request)
        if not response:
            response = self.get_response(request)
        if hasattr(self, "process_response"):
            response = self.process_response(request, response)
        return response


"""
Print sql on console for debug
"""

from django.db import connection  # NOQA: E402

from common.utils import print_sql  # NOQA: E402


class SQLPrintingMiddleware(MiddlewareMixin):
    """
    Middleware which prints out a list of all SQL queries done
    for each view that is processed. This is only useful for debugging.
    """

    def process_response(self, request, response):
        if (
            len(connection.queries) == 0
            or request.path_info.startswith("/favicon.ico")
            or request.path_info.startswith(settings.STATIC_URL)
            or request.path_info.startswith(settings.MEDIA_URL)
        ):
            return response

        filter_request = {}

        if (
            filter_request
            and "%s %s" % (request.method, request.path_info)
            not in filter_request
        ):
            return response

        indentation = 0
        separator = "\033[1;37m- \033[0m" * 50

        print(
            "\033[1;32m[REQUEST] \033[0m%s\033[1;35m[SQL Queries for]\033[1;34m %s %s\033[0m\n"
            % (" " * indentation, request.method, request.path_info)
        )

        total_time = 0.0
        for query in connection.queries:
            nice_sql = " "
            sql = "\033[1;31m[%s]\033[0m %s" % (query["time"], nice_sql)
            total_time = total_time + float(query["time"])

            print(
                "%s%s%s%s"
                % (
                    " " * indentation,
                    sql,
                    print_sql(query["sql"], True),
                    separator,
                )
            )

        replace_tuple = (
            " " * indentation,
            str(total_time),
            str(len(connection.queries)),
        )
        print(
            "%s\033[1;32m[TOTAL TIME: %s seconds (%s queries)]\033[0m"
            % replace_tuple
        )

        return response
