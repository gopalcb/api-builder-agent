"""Synthesize a REST API sample with encrypted caching for one public GET method."""

import json
import os
from pathlib import Path

from aws_cdk import App, Duration, Stack
from aws_cdk import aws_apigateway as gateway

policy = json.loads((Path(__file__).parent / "cache-policy.json").read_text())
app = App(outdir=os.environ.get("CDK_OUTDIR", "cdk.out"))
stack = Stack(app, "CachingSample")
api = gateway.RestApi(stack, "Api", deploy_options=gateway.StageOptions(
    cache_cluster_enabled=True, cache_cluster_size="0.5", caching_enabled=False,
    method_options={f'{policy["path"]}/GET': gateway.MethodDeploymentOptions(
        caching_enabled=True, cache_ttl=Duration.seconds(policy["ttl_seconds"]), cache_data_encrypted=True,
    )},
))
resource = api.root

for part in policy["path"].strip("/").split("/"):
    if part:
        resource = resource.add_resource(part)

keys = [f"method.request.querystring.{key}" for key in policy["query_keys"]]
resource.add_method("GET", gateway.MockIntegration(
    request_templates={"application/json": '{"statusCode": 200}'},
    integration_responses=[gateway.IntegrationResponse(status_code="200", response_templates={"application/json": '{"message":"Replace this public mock integration with your backend"}'})],
    cache_key_parameters=keys,
), request_parameters={key: False for key in keys}, method_responses=[gateway.MethodResponse(status_code="200")])
app.synth()
