"""Run the generated application's CRUD, inventory and local-auth contracts offline."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app import create_app
from services import logger_service
import json


class ProductApiTests(unittest.TestCase):
    """Exercise real Flask routing and SQLite storage without a model or network."""

    def setUp(self) -> None:
        """Create an isolated product API with one public route and protected mutations."""
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        attributes = [{'name': name, 'data_type': kind, 'nullable': False, 'description': name}
                      for name, kind in [('name', 'string'), ('price', 'decimal'), ('stock', 'integer')]]
        methods = {'list': 'GET', 'get': 'GET', 'create': 'POST', 'update': 'PATCH', 'sell': 'POST', 'delete': 'DELETE'}
        routes = [{'id': index + 1, 'entity': 'Product', 'operation': operation, 'method': method,
                   'path': '/product/' + operation, 'access': 'public' if operation == 'list' else 'authenticated'}
                  for index, (operation, method) in enumerate(methods.items())]
        self.app = create_app({'entities': [{'name': 'Product', 'attributes': attributes}], 'routes': routes},
                              str(Path(self.directory.name) / 'records.db'))
        self.app.config.update(TESTING=True, MOCK_AUTH=True)
        self.client = self.app.test_client()
        token = self.client.post('/auth/token').json['access_token']
        self.headers = {'Authorization': 'Bearer ' + token}

    def test_product_lifecycle(self) -> None:
        """Verify public read, protected writes, type validation and atomic stock updates."""
        self.assertEqual(self.client.get('/product/list').status_code, 200)
        self.assertEqual(self.client.post('/product/create', json={}).status_code, 401)
        self.assertEqual(self.client.get('/product/get', headers={'Authorization': 'Bearer invalid'}).status_code, 401)
        created = self.client.post('/product/create', headers=self.headers, json={'name': 'Product', 'price': 12.5, 'stock': 7})
        self.assertEqual(created.status_code, 201)
        record_id = created.json['id']
        query = '?id=' + record_id
        self.assertEqual(self.client.get('/product/get' + query, headers={**self.headers, 'Content-Type': 'application/json'}).json['stock'], 7)
        self.assertEqual(self.client.patch('/product/update' + query, headers=self.headers, json={'price': 14}).json['price'], 14)
        self.assertEqual(self.client.patch('/product/update' + query, headers=self.headers, json={'stock': True}).status_code, 400)
        self.assertEqual(self.client.patch('/product/update' + query, headers=self.headers, json={'stock': -1}).status_code, 400)

        def sell(unused: int) -> int:
            """Use independent request contexts for concurrent inventory requests."""
            with self.app.test_client() as client:
                return client.post('/product/sell' + query, headers=self.headers, json={'quantity': 5}).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(sell, range(2))), [200, 409])

        self.assertEqual(self.client.get('/product/get' + query, headers=self.headers).json['stock'], 2)
        self.assertEqual(self.client.delete('/product/delete' + query, headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get('/product/get' + query, headers=self.headers).status_code, 404)

    def test_request_logs(self) -> None:
        """Correlate successful and rejected requests without exposing record values."""
        response = self.client.post('/product/create', headers=self.headers,
                                    json={'name': 'PRIVATE_RECORD_SENTINEL', 'price': 2, 'stock': 1})
        denied = self.client.get('/product/get?secret=PRIVATE_QUERY_SENTINEL')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(denied.status_code, 401)
        content = logger_service.LOG_PATH.read_text()
        records = [json.loads(line) for line in content.splitlines()]
        success = [row for row in records if row.get('trace_id') == response.headers['X-Request-ID']]
        failure = [row for row in records if row.get('trace_id') == denied.headers['X-Request-ID']]
        self.assertTrue(any(row.get('function') == 'services.record_service.execute' for row in success))
        self.assertTrue(any(row['event'] == 'function.failed' and row['level'] == 'ERROR' for row in failure))
        self.assertTrue(any(row.get('status') == 401 for row in failure))
        self.assertNotIn('PRIVATE_RECORD_SENTINEL', content)
        self.assertNotIn('PRIVATE_QUERY_SENTINEL', content)

    def test_local_swagger_cors(self) -> None:
        """Permit loopback Swagger preflights while rejecting remote browser origins."""
        response = self.client.options('/product/create', headers={'Origin': 'http://127.0.0.1:4200',
            'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'Authorization, Content-Type'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Access-Control-Allow-Origin'], 'http://127.0.0.1:4200')
        self.assertEqual(self.client.post('/auth/token', headers={'Origin': 'https://example.com'}).status_code, 403)

    def test_mock_auth_must_be_enabled(self) -> None:
        """Fail closed when local authentication is not explicitly enabled."""
        self.app.config['MOCK_AUTH'] = False
        self.assertEqual(self.client.post('/auth/token').status_code, 403)
        self.assertEqual(self.client.post('/product/create', headers=self.headers, json={}).status_code, 403)
        self.assertEqual(self.client.get('/product/list').status_code, 200)


if __name__ == '__main__':
    unittest.main()
