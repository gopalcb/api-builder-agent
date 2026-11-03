# Named serverless starter

The generator writes project.json. Stack, Lambda, table and pool names use project-stage; S3 names and other physical IDs use CloudFormation uniqueness. Deploy each stage to its intended AWS account/region; do not rename an existing stack to migrate data.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests
.venv/bin/python app.py
# With an installed, compatible AWS CDK v2 CLI:
cdk diff
# Only when deployment is intended and the target account/region is configured:
cdk deploy
```

Synthesis requires no account lookups. Deployment requires AWS credentials, a selected account/region and CDK bootstrap. Data, assets, identity and logs are retained on stack deletion; retained named resources require an explicit import/recovery plan before recreating the stack.

CloudFront serves a private S3 origin with OAC. Upload a website separately; this starter has no website assets. API Gateway is a separate HTTP API endpoint with a JWT-protected GET /health; CloudFront does not proxy or cache this API. Handler response is no-store. The table is provisioned but no data permissions are granted until handlers need them.

Configure Cognito OAuth callback/logout URLs and a domain for your real frontend before login; no hosted login application is included. Users are administrator-created by default. Clients send an access token with the openid scope. Add explicit CORS origins when connecting a browser on another origin. The public client has no secret. App-level tenant/entity authorization must be implemented before real data routes.

Extend only as needed: SQS + DLQ for background work, EventBridge for events, Step Functions for durable jobs, ACM/Route 53 for custom domains, CloudWatch alarms and API access logs for operational readiness. No ECS. Infrastructure synthesis alone does not prove runtime login, permissions, CORS, website content or deployed health.
