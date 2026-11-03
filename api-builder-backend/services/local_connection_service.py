"""Permit credentialed local browser connections without broadening remote access."""

from flask import Response, jsonify, request

from validation import is_local_connection_origin

from services.logger_service import log_function, log_event, LogStep

ALLOWED_METHODS = {"GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS"}
ALLOWED_HEADERS = {"content-type", "x-project-id"}


@log_function
def check_local_connection() -> Response | tuple | None:
    """Reject foreign origins and finish preflights before project/user handlers."""
    origin = request.headers.get("Origin", "")

    if not origin or origin == request.host_url.rstrip("/"):
        return Response(status=204) if request.method == "OPTIONS" else None

    if not is_local_connection_origin(origin, request.host_url):
        return jsonify(error="Use the same localhost hostname and protocol as the backend."), 403

    if request.method == "OPTIONS":
        method = request.headers.get("Access-Control-Request-Method", "")
        headers = {value.strip().lower() for value in request.headers.get("Access-Control-Request-Headers", "").split(",") if value.strip()}

        if method not in ALLOWED_METHODS or not headers <= ALLOWED_HEADERS:
            return jsonify(error="Unsupported local connection request."), 403

        return Response(status=204)

    return None


@log_function
def add_local_connection_headers(response: Response) -> Response:
    """Expose responses to the matching local browser while retaining cookies."""
    origin = request.headers.get("Origin", "")
    response.vary.add("Origin")

    if is_local_connection_origin(origin, request.host_url):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = ", ".join(sorted(ALLOWED_METHODS))
        response.headers["Access-Control-Allow-Headers"] = ", ".join(sorted(ALLOWED_HEADERS))
        response.headers["Access-Control-Max-Age"] = "600"

    return response
