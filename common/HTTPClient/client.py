import json

import requests
import logging
from requests.adapters import HTTPAdapter, Retry
from urllib.parse import urlencode

from common.HTTPClient import exceptions

log = logging.getLogger(__name__)


class BaseClient:
    _DEFAULT_BASE_URL = None

    # TODO: Add init method

    @staticmethod
    def _generate_auth_url(path, params):
        """Returns the path and query string portion of the request URL, first
        adding any necessary parameters.

        :param path: The path portion of the URL.
        :type path: string

        :param params: URL parameters.
        :type params: dict or list of key/value tuples

        :rtype: string

        """

        if not params:
            return path

        if isinstance(params, dict):
            params = sorted(dict(**params).items())
        elif isinstance(params, (list, tuple)):
            params = params

        return (
            path + "?" + requests.utils.unquote_unreserved(urlencode(params))
        )

    def _request(
        self,
        url,
        get_params=None,
        post_params=None,
        retry_counter=5,
        dry_run=None,
    ):
        """Performs HTTP GET/POST with credentials, returning the body as
        JSON.

        param url: URL path for the request. Should begin with a slash.
        type url: string

        param get_params: HTTP GET parameters.
        type get_params: dict or list of tuples

        param post_params: HTTP POST parameters. Only specified by calling method.
        type post_params: dict

        param first_request_time: The time of the first request (None if no
            retries have occurred).
        type first_request_time: :class:`datetime.datetime`

        param retry_counter: The number of this retry, or zero for first attempt.
        type retry_counter: int

        param dry_run: If true, only prints URL and parameters. true or false.
        type dry_run: bool

        raises routingpy.exceptions.RouterError: when anything else happened while requesting.
        raises routingpy.exceptions.RouterApiError: when the API returns an error due to faulty configuration.
        raises routingpy.exceptions.JSONParseError: when the JSON response can't be parsed.
        raises routingpy.exceptions.Timeout: when the request timed out.

        returns: raw JSON response.
        rtype: dict
        """
        retries = Retry(
            total=retry_counter,
            backoff_factor=0.1,
            status_forcelist=[500, 502, 503, 504],
        )

        self._session.mount("https://", HTTPAdapter(max_retries=retries))

        authed_url = self._generate_auth_url(url, get_params)

        final_requests_kwargs = self.kwargs

        # Determine GET/POST.
        requests_method = self._session.get
        if post_params is not None:
            requests_method = self._session.post
            if (
                final_requests_kwargs["headers"]["Content-Type"]
                == "application/json"
            ):
                final_requests_kwargs["json"] = post_params
            else:
                # Send as x-www-form-urlencoded key-value pair string (e.g. Mapbox API)
                final_requests_kwargs["data"] = post_params

        # Only print URL and parameters for dry_run
        if dry_run:
            print(
                "url:\n{}\nParameters:\n{}".format(
                    self.base_url + authed_url,
                    json.dumps(final_requests_kwargs, indent=2),
                )
            )
            return

        try:

            log.debug(
                f"_request: requests_method({self.base_url + authed_url}, {final_requests_kwargs})"
            )

            response = requests_method(
                self.base_url + authed_url, **final_requests_kwargs
            )
            self._req = response.request

        except requests.exceptions.Timeout:
            raise exceptions.Timeout()

        result = self._get_body(response)

        log.debug(f"_request: result = {result}")

        return result

    @property
    def req(self):
        """Holds the :class:`requests.PreparedRequest` property for the last request."""
        return self._req

    @staticmethod
    def _get_body(response):
        status_code = response.status_code

        try:
            body = response.json()
        except json.decoder.JSONDecodeError:
            raise exceptions.JSONParseError(
                "Can't decode JSON response:{}".format(response.text)
            )

        if status_code != 200:
            raise exceptions.RouterError(status_code, body)

        return body
