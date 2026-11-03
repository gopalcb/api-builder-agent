"""Persist RBAC snapshots, run the registered agent and compile AWS policy exports."""

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import subprocess
from zipfile import ZipFile, ZipInfo

from flask import g
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
import yaml

from models import ProjectRbacConfiguration, db
from validation import validate_rbac_semantics
from runtime.worker import run_agent_worker

from services.logger_service import log_function, log_event, LogStep


class RbacError(Exception):
    """A safe RBAC failure with a response status."""

    def __init__(self, message: str, status: int = 400) -> None:
        """Attach a public message and HTTP status."""
        super().__init__(message)
        self.status = status


@log_function
def read_configuration() -> dict:
    """Return the saved snapshot or an explicit unconfigured state."""
    row = db.session.get(ProjectRbacConfiguration, g.project_id)

    return {"revision": row.revision, "configuration": row.document} if row else {"revision": 0, "configuration": None}


@log_function
def check_revision(revision: int) -> dict:
    """Reject operations based on an outdated saved revision."""
    saved = read_configuration()

    if saved["revision"] != revision:
        raise RbacError("Configuration changed. Reload the saved revision before continuing.", 409)

    return saved


@log_function
def save_configuration(configuration: dict, revision: int) -> dict:
    """Atomically create or replace the active project snapshot."""
    if revision == 0:
        db.session.add(ProjectRbacConfiguration(project_id=g.project_id, revision=1, document=configuration))
    else:
        result = db.session.execute(update(ProjectRbacConfiguration).where(
            ProjectRbacConfiguration.project_id == g.project_id, ProjectRbacConfiguration.revision == revision,
        ).values(revision=revision + 1, document=configuration))

        if result.rowcount != 1:
            raise RbacError("Configuration changed. Reload before saving.", 409)

    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise RbacError("Configuration changed. Reload before saving.", 409) from error

    return read_configuration()


@log_function
def run_rbac_agent(context: dict, timeout: int) -> dict:
    """Run the registered worker with a deadline and reap it on timeout."""
    try:
        return run_agent_worker("rbac-builder", context, timeout)
    except subprocess.TimeoutExpired as error:
        raise RbacError("RBAC generation timed out. Saved configuration was preserved.", 504) from error
    except RuntimeError as error:
        raise RbacError("RBAC generation failed. Check Codex sign-in and runtime.", 502) from error


@log_function
def generate_configuration(configuration: dict, prompt: str, revision: int, timeout: int) -> dict:
    """Return an unsaved proposal while keeping identity and route snapshots fixed."""
    check_revision(revision)
    db.session.rollback()
    try:
        proposal = run_rbac_agent({"configuration": configuration, "requirements": prompt}, timeout)
        draft = {**deepcopy(configuration), **proposal}
        validate_rbac_semantics(draft)
    except (OSError, ValueError) as error:
        raise RbacError("RBAC generation returned an invalid proposal or could not start. Saved configuration was preserved.", 502) from error

    check_revision(revision)

    return {"revision": revision, "configuration": draft}


@log_function
def preview_access(configuration: dict, roles: list, route: str) -> dict:
    """Evaluate the explicit matrix without claiming a live AWS authorization result."""
    definition = next((item for item in configuration["routes"] if item["key"] == route), None)
    public = definition is not None and definition["access"] == "public"
    allowed = public or any(grant["role"] in roles and grant["route"] == route for grant in configuration["grants"])

    return {"decision": "allow" if allowed else "deny", "mode": "configuration-preview", "public": public}


@log_function
def compile_artifacts(configuration: dict, revision: int) -> dict:
    """Compile explicit grants into CloudFormation and Cedar without model-generated code."""
    if not configuration["routes"] or configuration["questions"]:
        raise RbacError("Add routes and resolve proposal questions before exporting.")

    identity = configuration["identity"]
    snapshot_hash = sha256(json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    parameters = {
        "UserPoolId": {"Type": "String", "AllowedPattern": "[a-z]{2}(-[a-z]+)+-[0-9]+_[A-Za-z0-9]+"},
        "ClientId": {"Type": "String", "AllowedPattern": "[a-z0-9]{1,128}"},
    }

    if identity["user_pool_id"]:
        parameters["UserPoolId"]["Default"] = identity["user_pool_id"]

    if identity["client_id"]:
        parameters["ClientId"]["Default"] = identity["client_id"]

    schema = {"ApiBuilder": {
        "entityTypes": {
            "User": {"memberOfTypes": ["Group"], "shape": {"type": "Record", "attributes": {}}},
            "Group": {"shape": {"type": "Record", "attributes": {}}},
            "Api": {"shape": {"type": "Record", "attributes": {}}},
        },
        "actions": {route["key"]: {"appliesTo": {
            "principalTypes": ["User"], "resourceTypes": ["Api"],
            "context": {"type": "Record", "attributes": {}},
        }} for route in sorted(configuration["routes"], key=lambda item: item["key"]) if route["access"] != "public"},
    }}
    resources = {
        "PolicyStore": {"Type": "AWS::VerifiedPermissions::PolicyStore", "Properties": {
            "ValidationSettings": {"Mode": "STRICT"}, "Schema": {"CedarJson": json.dumps(schema, sort_keys=True)},
        }},
        "IdentitySource": {"Type": "AWS::VerifiedPermissions::IdentitySource", "Properties": {
            "PolicyStoreId": {"Ref": "PolicyStore"}, "PrincipalEntityType": "ApiBuilder::User",
            "Configuration": {"CognitoUserPoolConfiguration": {
                "UserPoolArn": {"Fn::Sub": "arn:${AWS::Partition}:cognito-idp:${AWS::Region}:${AWS::AccountId}:userpool/${UserPoolId}"},
                "ClientIds": [{"Ref": "ClientId"}], "GroupConfiguration": {"GroupEntityType": "ApiBuilder::Group"},
            }},
        }},
    }
    policies = []
    roles = {role["id"]: role for role in configuration["roles"]}

    for role in sorted(roles.values(), key=lambda item: item["id"]):
        if role["create_group"]:
            logical_id = "Group" + sha256(role["group"].encode()).hexdigest()[:20]
            resources[logical_id] = {"Type": "AWS::Cognito::UserPoolGroup", "Properties": {
                "GroupName": role["group"], "UserPoolId": {"Ref": "UserPoolId"}, "Description": role["description"],
            }}

    for grant in sorted(configuration["grants"], key=lambda item: (item["role"], item["route"])):
        group = roles[grant["role"]]["group"]
        statement = (
            'permit(principal in ApiBuilder::Group::"${UserPoolId}|' + group + '",\n'
            '  action == ApiBuilder::Action::' + json.dumps(grant["route"]) + ',\n'
            '  resource == ApiBuilder::Api::"api");'
        )
        logical_id = "Grant" + sha256((group + "\0" + grant["route"]).encode()).hexdigest()[:20]
        resources[logical_id] = {"Type": "AWS::VerifiedPermissions::Policy", "Properties": {
            "PolicyStoreId": {"Ref": "PolicyStore"}, "Definition": {"Static": {"Statement": {"Fn::Sub": statement}}},
        }}
        policies.append(statement)

    template = {
        "AWSTemplateFormatVersion": "2010-09-09", "Description": "API Builder RBAC configuration; runtime attachment required",
        "Metadata": {"SnapshotHash": snapshot_hash, "Revision": revision},
        "Parameters": parameters, "Resources": resources,
        "Outputs": {"PolicyStoreId": {"Value": {"Ref": "PolicyStore"}}},
    }
    readme = f'''# RBAC export — configuration only

Revision: {revision}
Snapshot SHA-256: {snapshot_hash}

This archive does not deploy or enforce authorization. Deploy cloudformation.yaml
in the existing Cognito pool's AWS account and region. Supply UserPoolId and ClientId
when omitted. Existing groups are referenced; only explicitly new groups are created.
Assign group membership administratively. No users or authentication pools are created.
policies.cedar is a template: replace ${{UserPoolId}} before standalone Cedar evaluation.
CloudFormation substitutes it automatically. Preserve the snapshot hash with deployment.

Runtime integration:
- Authenticate against this identity source, not the builder workspace login.
- Map a trusted HTTP method and matched route template to the exact exported action ID.
- Call IsAuthorizedWithToken with accessToken, the policy store ID, actionType
  ApiBuilder::Action, actionId from the route key, resource entityType ApiBuilder::Api
  and entityId api. Never accept caller-provided role/group claims or action overrides.
- Attach a Lambda authorizer to every protected API Gateway REST method, or enforce
  the decision in the generated server before its handler. Prevent backend bypass.
- Deny unknown routes and missing grants; fail closed on evaluation errors/outages.
- Public routes are omitted from policies and must be explicitly handled by routing.
- Disable authorizer caching initially. Validate expired/wrong-client tokens, absent
  groups, denied actions and service failures in a disposable stack before release.
- Group changes/revocation do not invalidate existing tokens here before expiry.

This is route-level RBAC, not tenant/row ownership. Builder management endpoints
remain local-only and need their own admin authorization before public exposure.
'''

    return {
        "rbac-config.yaml": yaml.safe_dump({"revision": revision, "snapshot_hash": snapshot_hash, "configuration": configuration}, sort_keys=True),
        "cloudformation.yaml": yaml.safe_dump(template, sort_keys=False),
        "schema.json": json.dumps(schema, indent=2, sort_keys=True),
        "policies.cedar": "\n\n".join(policies) + "\n", "README.md": readme,
    }


@log_function
def export_configuration(revision: int) -> BytesIO:
    """Package a saved revision reproducibly without filesystem side effects."""
    saved = check_revision(revision)

    if saved["configuration"] is None:
        raise RbacError("Save a configuration before exporting.")

    artifacts = compile_artifacts(saved["configuration"], revision)
    archive = BytesIO()

    with ZipFile(archive, "w") as bundle:
        for name, content in artifacts.items():
            bundle.writestr(ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), content)

    archive.seek(0)

    return archive
