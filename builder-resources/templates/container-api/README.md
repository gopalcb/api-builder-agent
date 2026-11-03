# Local API

Run `docker compose up --build -d`. The API is exposed only on http://127.0.0.1:8080.

Get a test token with `curl -X POST http://127.0.0.1:8080/auth/token`. Send its `access_token` as `Authorization: Bearer <token>` for authenticated endpoints. Tokens expire after one hour and are invalidated on restart. This is mock authentication for localhost testing only; no production authentication is implemented.

Use the routes in `openapi.json`. Create accepts the entity attributes as JSON; list returns `items`; get/update/delete accept `id` in the query or configured `{id}` path. Sell accepts `{"quantity":1}` and an id, and atomically decrements integer `stock` (or `quantity`). Insufficient stock returns 409. Prices and stock cannot be negative. Entity IDs are strings; the API creates a UUID when omitted.

Data persists in the Compose named volume. `docker compose down` preserves it. Do not expose this mock issuer to a public network. No cloud infrastructure is generated. Search, RBAC and caching proposals require separate implementation and are not claimed as runtime features.

## Logs

Application logs are JSON lines in `logs/log-yyyy-mm-dd-N` (no extension).
Each application start reserves the next index for that calendar day, starting
at 1. Docker Compose binds this folder to `/app/logs`, so logs survive container
recreation and remain visible in the project. UTC timestamps, INFO/ERROR levels,
request trace IDs, nested function spans, durations, statuses and safe error-stack
locations show the full request flow. `X-Request-ID` on each response identifies
its trace. Filter with `rg '<request-id>' logs/log-yyyy-mm-dd-N`.

Payloads, bearer tokens, cookies and raw exception messages are not logged. Logs
are excluded from Git and image builds. Files are retained until you remove them;
no automatic retention policy or daily rollover is configured. Filenames use the
process's local date (UTC in the default container). The startup file remains in
use until that process exits. Ensure `logs/` is writable by container UID 10001
when running on Linux hosts with bind-mount ownership enforcement.
