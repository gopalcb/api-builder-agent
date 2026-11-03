"""One end-to-end workflow for the screen's two-column entity-name catalog."""

from sqlalchemy import inspect

from app import create_app
from models import db


def test_entity_names_end_to_end(tmp_path) -> None:
    """Create and reload names unchanged, enforcing only the JSON-object payload check."""
    config = {"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'names.db'}"}
    app = create_app(config)
    client = app.test_client()
    client.environ_base["HTTP_X_PROJECT_ID"] = "1"

    with app.app_context():
        assert [column["name"] for column in inspect(db.engine).get_columns("entities")] == ["id", "name"]

    assert client.get("/api/entities").json == {"entities": []}

    response = client.post("/api/entities", json={"name": " Customer account ", "definition": "ignored draft"})

    assert response.status_code == 201, response.json

    entity = response.json["entity"]

    assert set(entity) == {"id", "name"} and entity["name"] == "Customer account"

    other = create_app(config).test_client()
    other.set_cookie("user_id", client.get_cookie("user_id").value)
    other.environ_base["HTTP_X_PROJECT_ID"] = "1"

    assert other.get("/api/entities").json == {"entities": [entity]}
    assert client.post("/api/entities", json={"name": " CUSTOMER ACCOUNT "}).status_code == 409
    assert client.post("/api/entities", json=[]).status_code == 400
    assert client.get("/entities").json == {"entities": [entity]}
