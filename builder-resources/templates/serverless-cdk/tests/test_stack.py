"""Check the synthesized starter's security and service boundaries offline."""

import tempfile
import unittest

from aws_cdk import App
from aws_cdk.assertions import Match, Template

from stack import ServerlessStack


class StackTests(unittest.TestCase):
    """Exercise the real construct graph without AWS credentials."""

    def test_serverless_security(self) -> None:
        """Keep storage private, routes authorized and state retained."""
        with tempfile.TemporaryDirectory() as directory:
            app = App(outdir=directory)
            stack = ServerlessStack(app, "orders-test", {"project": "orders", "stage": "test"})
            template = Template.from_stack(stack)
            template.resource_count_is("AWS::Lambda::Function", 1)
            template.resource_count_is("AWS::ECS::Service", 0)
            template.has_resource_properties("AWS::S3::Bucket", {
                "PublicAccessBlockConfiguration": {
                    "BlockPublicAcls": True, "BlockPublicPolicy": True,
                    "IgnorePublicAcls": True, "RestrictPublicBuckets": True,
                },
            })
            template.has_resource("AWS::DynamoDB::Table", {"DeletionPolicy": "Retain"})
            template.has_resource_properties("AWS::DynamoDB::Table", {"TableName": "orders-test-data", "BillingMode": "PAY_PER_REQUEST"})
            template.has_resource_properties("AWS::ApiGatewayV2::Route", {"AuthorizationType": "JWT", "AuthorizationScopes": ["openid"]})
            template.has_resource_properties("AWS::Cognito::UserPoolClient", {"GenerateSecret": False})
            template.resource_count_is("AWS::CloudFront::OriginAccessControl", 1)
            template.has_resource_properties("AWS::CloudFront::CachePolicy", {"CachePolicyConfig": Match.object_like({"MinTTL": 0})})
            app.synth()


if __name__ == "__main__":
    unittest.main()
