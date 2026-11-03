"""One end-to-end API workflow with the external generation boundary mocked."""

from copy import deepcopy
from unittest.mock import MagicMock

from app import create_app
from services import entity_service as service


def test_entity_api_end_to_end(tmp_path, monkeypatch) -> None:
    """Create, generate, read, regenerate and preserve data when generation fails."""
    config = {"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'entities.db'}"}
    client = create_app(config).test_client()
    customer_response = client.post("/create-entity", json={"name": "Customer"})
    order_response = client.post("/api/create-entity", json={"name": "Order", "description": "Purchase"})

    assert customer_response.status_code == 201, customer_response.json
    assert order_response.status_code == 201, order_response.json

    customer_id = customer_response.json["entity"]["id"]
    order_id = order_response.json["entity"]["id"]
    generated = {
        "entity_id": order_id,
        "attributes": [{"name": "total", "data_type": "decimal", "nullable": False, "description": "Total"}],
        "relationships": [{"name": "customer", "target_entity_id": customer_id, "relationship_type": "many_to_one", "description": "Buyer"}],
    }
    worker = MagicMock(return_value=generated)
    monkeypatch.setattr(service, "run_entity_agent", worker)
    payload = {"entity_id": order_id, "prompt": "Add a total and customer relationship"}
    response = client.post("/api/generate-entity-attributes", json=payload)

    assert response.status_code == 200, response.json

    entity = response.json["entity"]

    assert entity["attributes"] == generated["attributes"], "Generated attributes were not persisted"
    assert entity["relationships"] == generated["relationships"], "Generated relationship was not persisted"

    context, _ = worker.call_args.args

    assert context["entity_id"] == order_id and context["prompt"] == payload["prompt"]
    assert {item["id"] for item in context["existing_entities"]} == {customer_id, order_id}

    # A new app verifies database persistence, not just the current request state.
    reader = create_app(config).test_client()

    assert reader.get(f"/entities/{order_id}").json["entity"] == entity

    regenerated = client.post("/generate-entity-attributes", json=payload)

    assert regenerated.status_code == 200, regenerated.json

    saved = regenerated.json["entity"]

    assert saved["revision"] == 2 and saved["attributes"] == generated["attributes"]
    assert saved["relationships"] == generated["relationships"], "Regeneration duplicated relationships"

    invalid = deepcopy(generated)
    invalid["attributes"][0]["nullable"] = "not-a-boolean"
    worker.return_value = invalid
    failed = client.post("/generate-entity-attributes", json=payload)

    assert failed.status_code == 502, "Malformed generated schemas must be rejected"
    assert reader.get(f"/entities/{order_id}").json["entity"] == saved, "Failed generation changed stored data"


    for duplicate_name in ('total', 'TOTAL'):
        duplicate = deepcopy(generated)
        duplicate['attributes'].append({**duplicate['attributes'][0], 'name': duplicate_name})
        worker.return_value = duplicate
        failed = client.post('/generate-entity-attributes', json=payload)

        assert failed.status_code == 502
        assert 'Duplicate attribute' in failed.json['error']
        assert reader.get(f'/entities/{order_id}').json['entity'] == saved
