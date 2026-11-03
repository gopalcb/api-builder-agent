"""Compose serverless storage, identity, API and static delivery using CDK L2 constructs."""

from pathlib import Path

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigatewayv2 as apigateway
from aws_cdk import aws_apigatewayv2_authorizers as authorizers
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct


class ServerlessStack(Stack):
    """Provide a retained, named baseline without containers or network lookups."""

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        """Wire one authenticated sample route and a private static origin."""
        super().__init__(scope, construct_id, **kwargs)
        prefix = f'{config["project"]}-{config["stage"]}'
        bucket = s3.Bucket(
            self, "Assets", block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED, enforce_ssl=True,
            versioned=True, removal_policy=RemovalPolicy.RETAIN,
        )
        table = dynamodb.Table(
            self, "Data", table_name=f"{prefix}-data",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(point_in_time_recovery_enabled=True),
            removal_policy=RemovalPolicy.RETAIN,
        )
        pool = cognito.UserPool(
            self, "Identity", user_pool_name=f"{prefix}-users", self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            removal_policy=RemovalPolicy.RETAIN,
        )
        client = pool.add_client("WebClient", generate_secret=False)
        log_group = logs.LogGroup(
            self, "ApiLogs", retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.RETAIN,
        )
        function = lambda_.Function(
            self, "Handler", function_name=f"{prefix}-api",
            runtime=lambda_.Runtime.PYTHON_3_12, handler="handler.handle_request",
            code=lambda_.Code.from_asset(str(Path(__file__).parent / "lambda")),
            timeout=Duration.seconds(15), memory_size=256, log_group=log_group,
            environment={"TABLE_NAME": table.table_name},
        )
        # The sample handler reads no data; grant only the operations a real route needs.
        api = apigateway.HttpApi(self, "Api", api_name=f"{prefix}-api")
        api.add_routes(
            path="/health", methods=[apigateway.HttpMethod.GET],
            integration=integrations.HttpLambdaIntegration("HandlerIntegration", function),
            authorizer=authorizers.HttpUserPoolAuthorizer("UserPoolAuthorizer", pool, user_pool_clients=[client]),
            authorization_scopes=["openid"],
        )
        cache_policy = cloudfront.CachePolicy(
            self, "StaticCache", min_ttl=Duration.seconds(0),
            default_ttl=Duration.seconds(60), max_ttl=Duration.days(1),
            enable_accept_encoding_gzip=True, enable_accept_encoding_brotli=True,
        )
        distribution = cloudfront.Distribution(
            self, "Delivery", default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cache_policy,
                response_headers_policy=cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
            ),
        )

        for name, value in {
            "ApiUrl": api.api_endpoint, "AssetsBucket": bucket.bucket_name,
            "DistributionId": distribution.distribution_id,
            "SiteUrl": f"https://{distribution.distribution_domain_name}",
            "UserPoolId": pool.user_pool_id, "ClientId": client.user_pool_client_id,
            "TableName": table.table_name,
        }.items():
            CfnOutput(self, name, value=value)
