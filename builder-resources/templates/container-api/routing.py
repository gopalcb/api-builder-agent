"""Register only reviewed endpoints and an explicit local mock token issuer."""

from functools import partial
import re

from flask import current_app, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.exceptions import BadRequest, Forbidden, Unauthorized

from services.record_service import execute

from services.logger_service import log_function, log_event, LogStep


@log_function
def register_routes(app, configuration: dict) -> None:
    """Install configured routes without interpreting prompts as executable code."""
    app.before_request(check_local_origin)
    app.after_request(local_cors)
    entities = {entity['name']: entity for entity in configuration['entities']}
    app.add_url_rule('/health', 'health', lambda: jsonify(status='ok', authentication='local-mock'), methods=['GET'])
    app.add_url_rule('/auth/token', 'token', issue_token, methods=['POST'])

    for route in configuration['routes']:
        path = route['path'].replace('{id}', '<record_id>')
        app.add_url_rule(path, f"endpoint_{route['id']}", partial(dispatch, route, entities[route['entity']]), methods=[route['method']])


@log_function
def issue_token() -> tuple:
    """Issue a short-lived synthetic identity only when local mode is explicitly enabled."""
    if not current_app.config['MOCK_AUTH']:
        raise Forbidden('Local mock authentication is disabled.')

    token = URLSafeTimedSerializer(current_app.secret_key, salt='local-mock').dumps({'sub': 'local-tester'})

    return jsonify(access_token=token, token_type='Bearer', expires_in=3600, mode='local-mock'), 200


@log_function
def dispatch(route: dict, entity: dict, record_id: str | None = None) -> tuple:
    """Authenticate first, then validate and execute the configured operation."""
    if route['access'] == 'authenticated':
        if not current_app.config['MOCK_AUTH']:
            raise Forbidden('Local mock authentication is disabled.')

        authorization = request.headers.get('Authorization', '')

        if not authorization.startswith('Bearer '):
            raise Unauthorized('A local mock bearer token is required.')

        try:
            URLSafeTimedSerializer(current_app.secret_key, salt='local-mock').loads(authorization[7:], max_age=3600)
        except (BadSignature, SignatureExpired) as error:
            raise Unauthorized('Invalid or expired local token.') from error

    payload = request.get_json() if request.is_json and request.content_length else {}

    if not isinstance(payload, dict):
        raise BadRequest('Send a JSON object.')

    record_id = record_id or request.args.get('id') or payload.get('id')
    result, status = execute(current_app.config['DATABASE'], entity, route['operation'], payload, record_id)

    return jsonify(result), status



@log_function
def check_local_origin() -> None:
    """Accept browser calls only from loopback origins in this local test runtime."""
    origin = request.headers.get('Origin')

    if origin and not re.fullmatch(r'http://(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?', origin):
        raise Forbidden('Only localhost browser origins are supported.')


@log_function
def local_cors(response):
    """Allow local Swagger to send bearer credentials without allowing remote sites."""
    origin = request.headers.get('Origin', '')

    if re.fullmatch(r'http://(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?', origin):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PATCH, DELETE, OPTIONS'
        response.vary.add('Origin')

    return response
