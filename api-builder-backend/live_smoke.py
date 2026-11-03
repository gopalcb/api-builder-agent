"""Opt-in live Codex/Deep Agents smoke check using a disposable SQLite database."""

from tempfile import TemporaryDirectory

from app import create_app


def main() -> None:
    """Exercise both routes and verify a real generated relationship is persisted."""
    with TemporaryDirectory(prefix="entity-smoke-") as folder:
        app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{folder}/test.db",
            "ENTITY_AGENT_TIMEOUT": 120,
        })
        client = app.test_client()
        target = client.post("/create-entity", json={"name": "Customer"}).json["entity"]
        source = client.post("/create-entity", json={"name": "Order"}).json["entity"]
        response = client.post("/generate-entity-attributes", json={
            "entity_id": source["id"],
            "prompt": f"Add a required decimal total and a many_to_one customer relationship to Customer entity {target['id']}.",
        })
        print("Live generation HTTP status:", response.status_code)

        if response.status_code != 200:
            raise RuntimeError(response.json["error"])

        entity = response.json["entity"]

        assert client.get(f"/entities/{source['id']}").json == response.json
        assert any(item["target_entity_id"] == target["id"] for item in entity["relationships"])
        assert any(item["name"] == "total" and item["data_type"] == "decimal" for item in entity["attributes"])

        print("Verified live attributes, relationship and database readback.")


if __name__ == "__main__":
    main()
