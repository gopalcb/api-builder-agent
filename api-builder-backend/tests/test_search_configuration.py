"""Search proposals validate intent and handle worker failures without executing output."""

import subprocess
from unittest.mock import MagicMock

import pytest
from jsonschema import ValidationError, validate

from app import create_app
import routing
from runtime.registry import AGENTS


@pytest.mark.parametrize("kind,ranking", [("embedding", "none"), ("semantic", "vector"), ("regular", "lexical"), ("hybrid", "rrf")])
def test_search_workflow_schema(kind, ranking) -> None:
    """Each draft/review step constrains embedding and ranking to the selected type."""
    registration = AGENTS["search-builder"]
    runtime = MagicMock()
    runtime.output_schema = registration.load_schema()
    proposal = {
        "summary": "Search products", "source": "Product index to confirm", "fields": ["description"],
        "embedding": None if kind == "regular" else {"model": "Confirm existing model", "dimensions": "Match index", "chunking": "By paragraph"},
        "ranking": ranking, "request": "query text", "response": "ranked IDs", "steps": ["Check tenant scope"],
        "requirements": ["Confirm index and authorization filters"],
    }

    def run(prompt, context, schema):
        """Apply the real response schema without making a model request."""
        validate(proposal, schema)

        return proposal

    runtime.run.side_effect = run
    result = registration.create_workflow().run({"type": kind, "path": "/products/search", "prompt": "Search descriptions"}, runtime)

    assert result == proposal
    assert runtime.run.call_count == 2
    assert runtime.run.call_args.args[1]["draft"] == proposal
    schema = runtime.run.call_args.args[2]

    with pytest.raises(ValidationError):
        validate({**proposal, "ranking": "incorrect"}, schema)

    if kind == "regular":
        with pytest.raises(ValidationError):
            validate({**proposal, "embedding": {"model": "unexpected"}}, schema)


def test_search_api(tmp_path, monkeypatch) -> None:
    """Validate request bounds and expose safe errors while retaining no configuration."""
    client = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'search.db'}"}).test_client()
    client.environ_base["HTTP_X_PROJECT_ID"] = "1"
    worker = MagicMock(return_value={"summary": "Proposal"})
    monkeypatch.setattr(routing, "run_agent_worker", worker)
    payload = {"type": "hybrid", "path": "/products/search", "prompt": "Find products"}
    response = client.post("/api/generate-search-configuration", json=payload)

    assert response.status_code == 200
    assert response.json["configuration"]["summary"] == "Proposal"
    assert worker.call_args.args[0] == "search-builder"
    assert worker.call_args.args[1]["entities"] == []

    for invalid in [[], {}, {**payload, "type": "sql"}, {**payload, "path": "/../bad"},
                    {**payload, "prompt": " "}, {**payload, "prompt": "x" * 4001}, {**payload, "secret": "unexpected"}]:
        assert client.post("/api/generate-search-configuration", json=invalid).status_code == 400

    for failure, status in [(subprocess.TimeoutExpired("worker", 1), 504), (RuntimeError("private details"), 502)]:
        worker.side_effect = failure
        failed = client.post("/api/generate-search-configuration", json=payload)

        assert failed.status_code == status
        assert "private details" not in failed.json["error"]
