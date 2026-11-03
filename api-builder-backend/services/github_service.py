"""Publish an existing tested starter via GitHub REST without persisting credentials."""

from io import BytesIO
import json
import re
from urllib.request import Request, urlopen
from urllib.parse import quote
from zipfile import ZipFile

from werkzeug.exceptions import BadRequest

from models import ProjectRepository, db
from services.project_build_service import ready_build

from services.logger_service import log_function, log_event, LogStep


@log_function
def github_request(token: str, method: str, path: str, payload: dict | None = None) -> dict:
    """Send credentials only to GitHub's fixed API host; errors are translated by the route."""
    request = Request('https://api.github.com' + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json', 'User-Agent': 'API-Builder'})

    with urlopen(request, timeout=30) as response:
        return json.load(response)


@log_function
def push_project(project, payload: dict) -> dict:
    """Create a private repository if requested, then append a non-force build commit."""
    if not isinstance(payload, dict):
        raise BadRequest('Provide repository settings.')

    token, owner, name = (payload.get(key, '') for key in ('token', 'owner', 'name'))

    if not isinstance(token, str) or not token.strip() or len(token) > 1000 or '\n' in token or '\r' in token:
        raise BadRequest('Provide a GitHub access token.')

    if not isinstance(owner, str) or (owner and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}', owner)):
        raise BadRequest('Use a valid GitHub account or organization name.')

    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', name):
        raise BadRequest('Use a valid repository name.')

    if type(payload.get('create')) is not bool:
        raise BadRequest('Choose whether to create a new private repository.')

    artifact = ready_build(project)
    user = github_request(token, 'GET', '/user')
    owner = owner or user['login']
    base = f'/repos/{owner}/{name}'

    if payload['create']:
        repository = github_request(token, 'POST', '/user/repos' if owner.lower() == user['login'].lower() else f'/orgs/{owner}/repos',
                                    {'name': name, 'private': True, 'auto_init': True, 'description': project.summary[:350]})
    else:
        repository = github_request(token, 'GET', base)

    branch = repository['default_branch']
    # GitHub branch names can contain slashes; encode the whole branch as one URL segment.
    branch_path = quote(branch, safe='')
    head = github_request(token, 'GET', base + '/git/ref/heads/' + branch_path)['object']['sha']
    commit = github_request(token, 'GET', base + '/git/commits/' + head)

    with ZipFile(BytesIO(artifact.archive)) as bundle:
        tree = [{'path': name, 'mode': '100644', 'type': 'blob', 'content': bundle.read(name).decode()} for name in bundle.namelist()]

    tree_sha = github_request(token, 'POST', base + '/git/trees', {'base_tree': commit['tree']['sha'], 'tree': tree})['sha']
    commit_sha = github_request(token, 'POST', base + '/git/commits',
        {'message': 'Build project with API Builder', 'tree': tree_sha, 'parents': [head]})['sha']
    github_request(token, 'PATCH', base + '/git/refs/heads/' + branch_path, {'sha': commit_sha, 'force': False})
    row = db.session.get(ProjectRepository, project.id) or ProjectRepository(project_id=project.id)
    row.owner, row.name, row.url = owner, name, f'https://github.com/{owner}/{name}'
    db.session.add(row)
    db.session.commit()

    return {'owner': owner, 'name': name, 'url': row.url, 'commit': commit_sha}
