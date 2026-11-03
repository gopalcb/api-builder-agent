"""Generated read-only load scenario for the selected project's list endpoints."""

import json
import logging
import os

import requests
from locust import HttpUser, between, task
from locust.exception import StopUser

ROUTES = json.loads('__ROUTES_JSON__')
logger = logging.getLogger('api_builder.load_testing')


class ProjectUser(HttpUser):
    """Authenticate locally once, then exercise each selected read endpoint."""

    wait_time = between(float(os.environ['WAIT_MIN']), float(os.environ['WAIT_MAX']))

    def on_start(self):
        """Keep short-lived credentials in memory and out of generated artifacts."""
        logger.info('load_user.start')
        if any(route['access'] == 'authenticated' for route in ROUTES):
            try:
                response = requests.post(self.host.rstrip('/') + '/auth/token', timeout=10, allow_redirects=False)
                response.raise_for_status()
                token = response.json()['access_token']
            except (requests.RequestException, ValueError, KeyError) as error:
                logger.error('load_user.authentication_failed type=%s', type(error).__name__)
                raise StopUser() from error

            self.client.headers['Authorization'] = 'Bearer ' + token

    @task
    def read_endpoints(self):
        """Record HTTP and JSON contract failures without logging response bodies."""
        for route in ROUTES:
            with self.client.get(route['path'], name=route['path'], catch_response=True,
                                 timeout=10, allow_redirects=False) as response:
                if response.status_code != 200:
                    response.failure('Expected HTTP 200')
                    logger.error('load_request.failed path=%s status=%s', route['path'], response.status_code)
                    continue

                try:
                    payload = response.json()
                except ValueError:
                    response.failure('Expected JSON response')
                    continue

                if not isinstance(payload, dict) or not isinstance(payload.get('items'), list):
                    response.failure('Expected a list response with items')
