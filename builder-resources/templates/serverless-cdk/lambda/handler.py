"""Return a private health response behind the API Gateway JWT authorizer."""

import json


def handle_request(event: dict, context: object) -> dict:
    """Return no user data and prevent downstream response caching."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps({"status": "ok"}),
    }
