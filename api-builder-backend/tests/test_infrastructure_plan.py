"""Check infrastructure intent, project isolation and bounded worker failure behavior."""

import subprocess
from unittest.mock import MagicMock

import pytest
from jsonschema import ValidationError, validate

from app import create_app
import routing
from runtime.registry import AGENTS

PAYLOAD = {"platform": "aws", "deployment_mode": "serverless", "environment": "dev", "requirements": ""}
PROPOSAL = {
    "summary": "Proposed serverless API",
    "services": {"sqs": False, "sns": False, "redis": False},
    "recommendations": ["Use least-privilege IAM per function."],
    "requirements": ["Confirm deployment region."],
}


def test_infrastructure_workflow() -> None:
    """Exercise both steps with the actual schema and reject unsupported output."""
    registration = AGENTS["infrastructure-builder"]
    runtime = MagicMock()
    runtime.output_schema = registration.load_schema()

    def run(prompt, context):
        """Use the real contract at the mocked model boundary."""
        validate(PROPOSAL, runtime.output_schema)

        return PROPOSAL

    runtime.run.side_effect = run
    result = registration.create_workflow().run({**PAYLOAD, "entities": [], "caching": None}, runtime)

    assert result == PROPOSAL
    assert runtime.run.call_count == 2
    assert runtime.run.call_args.args[1]["draft"] == PROPOSAL

    for invalid in [{**PROPOSAL, "services": {"alb": True}}, {**PROPOSAL, "recommendations": []},
                    {**PROPOSAL, "services": {"sqs": "true", "sns": False, "redis": False}}]:
        with pytest.raises(ValidationError):
            validate(invalid, runtime.output_schema)


def test_infrastructure_api(tmp_path, monkeypatch) -> None:
    """Source entities from the selected owned project, reject extra fields and translate errors."""
    client = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'infra.db'}"}).test_client()
    project_id = client.get("/api/projects").json["default_project_id"]
    headers = {"X-Project-ID": str(project_id)}
    entity = client.post("/api/entities", headers=headers, json={"name": "Customer"}).json["entity"]
    other_id = client.post("/api/projects", json={"name": "Other", "summary": "Separate scope"}).json["project"]["id"]
    worker = MagicMock(return_value=PROPOSAL)
    monkeypatch.setattr(routing, "run_agent_worker", worker)

    response = client.post("/api/generate-infrastructure-plan", headers=headers, json=PAYLOAD)

    assert response.status_code == 200
    assert response.json == {"proposal": PROPOSAL}
    assert worker.call_args.args[0] == "infrastructure-builder"
    assert worker.call_args.args[1]["entities"] == [entity]
    assert worker.call_args.args[1]["caching"] is None
    assert client.post("/api/generate-infrastructure-plan", json=PAYLOAD).status_code == 400

    cache = {"kind": "gateway", "path": "/catalog", "method": "GET", "access": "public",
             "ttl_seconds": 60, "api_type": "rest", "query_keys": []}
    saved = client.put("/api/caching", headers=headers, json={"revision": 0, "configuration": cache})

    assert saved.status_code == 200
    client.post("/api/generate-infrastructure-plan", headers=headers, json=PAYLOAD)

    assert worker.call_args.args[1]["caching"] == cache

    other = client.post("/api/generate-infrastructure-plan", headers={"X-Project-ID": str(other_id)}, json=PAYLOAD)

    assert other.status_code == 200
    assert worker.call_args.args[1]["entities"] == []

    for invalid in [[], {}, {**PAYLOAD, "deployment_mode": "containerized"},
                    {**PAYLOAD, "platform": "azure"}, {**PAYLOAD, "environment": "bad"},
                    {**PAYLOAD, "requirements": "x" * 4001}, {**PAYLOAD, "entities": [entity]}]:
        assert client.post("/api/generate-infrastructure-plan", headers=headers, json=invalid).status_code == 400

    for failure, status in [(subprocess.TimeoutExpired("worker", 1), 504), (RuntimeError("private details"), 502)]:
        worker.side_effect = failure
        failed = client.post("/api/generate-infrastructure-plan", headers=headers, json=PAYLOAD)

        assert failed.status_code == status
        assert "private details" not in failed.json["error"]
