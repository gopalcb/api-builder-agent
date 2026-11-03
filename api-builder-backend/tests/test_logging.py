"""Verify atomic run allocation, process correlation, safe errors and request isolation."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def execute_script(script: str, directory: Path) -> dict:
    """Run a fresh logger process so tests do not replace the server's active handler."""
    result = subprocess.run([sys.executable, '-c', script, str(directory)], cwd=ROOT,
                            env={**os.environ, 'PYTHONPATH': f'{ROOT}:{ROOT / "api-builder-backend"}'},
                            capture_output=True, text=True, check=True)

    return json.loads(result.stdout)


def test_atomic_run_indexes(tmp_path) -> None:
    """Simultaneous starts reserve distinct, contiguous files and restart increments."""
    script = "import runtime,sys,json; from shared.logging_service import configure_logging; print(json.dumps(configure_logging(sys.argv[1]).name))"

    with ThreadPoolExecutor(max_workers=6) as pool:
        names = list(pool.map(lambda unused: execute_script(script, tmp_path), range(6)))

    assert sorted(int(name.rsplit('-', 1)[1]) for name in names) == list(range(1, 7))
    assert execute_script(script, tmp_path).endswith('-7')
    assert len(list(tmp_path.iterdir())) == 7


def test_inherited_worker_trace_and_safe_errors(tmp_path) -> None:
    """Keep child events in the parent's file and never log arguments or exception text."""
    script = '''
import json,sys,subprocess,runtime
from shared.logging_service import configure_logging,LogStep,worker_environment
path=configure_logging(sys.argv[1])
with LogStep('parent.request'):
    child="""import json,runtime
from shared.logging_service import configure_logging,LOG_CONTEXT,log_function
import os
from pathlib import Path
configure_logging(Path(os.environ['API_BUILDER_LOG_FILE']).parent,os.environ['API_BUILDER_LOG_FILE'])
LOG_CONTEXT.set(json.loads(os.environ['API_BUILDER_LOG_CONTEXT']))
@log_function
def fail(secret):
    raise ValueError(secret)
try:
    fail('SECRET_PAYLOAD_MUST_NOT_APPEAR')
except ValueError:
    pass
print(json.dumps({'ok':True}))
"""
    result=subprocess.run([sys.executable,'-c',child],env=worker_environment(),capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)=={'ok':True}
print(json.dumps(str(path)))
'''
    path = Path(execute_script(script, tmp_path))
    content = path.read_text()
    records = [json.loads(line) for line in content.splitlines()]
    failure = next(record for record in records if record['event'] == 'function.failed')
    parent = next(record for record in records if record.get('function') == 'parent.request')
    assert failure['trace_id'] == parent['trace_id']
    assert failure['parent_span_id'] == parent['span_id']
    assert failure['level'] == 'ERROR' and failure['error_type'] == 'ValueError'
    assert failure['stack'] and failure['duration_ms'] >= 0
    assert 'SECRET_PAYLOAD_MUST_NOT_APPEAR' not in content
    assert len(list(tmp_path.iterdir())) == 1
    assert len({record['pid'] for record in records}) == 2


def test_http_request_trace_and_build_phases(tmp_path) -> None:
    """Trace real HTTP/build functions and isolate consecutive requests without payload leakage."""
    script = '''
import json,sys,runtime
from shared.logging_service import configure_logging,LOG_CONTEXT
path=configure_logging(sys.argv[1])
from app import create_app
app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:'})
client=app.test_client()
a=client.get('/api/projects?secret=SECRET_HTTP_PAYLOAD')
b=client.post('/api/projects/1/build')
c=client.put('/api/endpoints',headers={'X-Project-ID':'1'},json={'password':'SECRET_HTTP_PAYLOAD'})
assert a.status_code==200 and b.status_code==200 and c.status_code==400
assert a.headers['X-Request-ID']!=b.headers['X-Request-ID']
assert LOG_CONTEXT.get()=={}
print(json.dumps({'path':str(path),'build_trace':b.headers['X-Request-ID']}))
'''
    result = execute_script(script, tmp_path)
    content = Path(result['path']).read_text()
    records = [json.loads(line) for line in content.splitlines()]
    build = [record for record in records if record.get('trace_id') == result['build_trace']]
    functions = {record.get('function') for record in build}
    assert {'build.render', 'build.validate_and_test', 'build.archive', 'build.persist'} <= functions
    assert any(record['event'] == 'request.completed' and record['status'] == 400 and record['level'] == 'ERROR' for record in records)
    assert 'SECRET_HTTP_PAYLOAD' not in content
