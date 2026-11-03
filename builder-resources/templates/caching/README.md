# Caching integration template

This export is the saved project revision, not an enabled cache. Inspect cache-policy.json. Only explicitly public GET routes are supported. Do not attach shared caching to authentication, user/tenant data or administrative routes. Builder configuration APIs remain local-only.

## Route / Redis

Install requirements in a virtual environment, then run `python example.py` and request the configured path at http://127.0.0.1:5055 twice with identical headers. X-Cache changes MISS → HIT; the timestamp stays fixed until expiry. This demonstrates caching locally without modifying your application. For Redis provide REDIS_URL privately in the runtime environment; use rediss:// with validated TLS for remote connections. No Redis instance or credentials are provisioned by this export.

Integrate cached_response(policy, cache) below your existing Flask route decorator. Requests carrying cookies or Authorization bypass caching. Exact query strings and request headers participate in the key. Only nonstreaming 200 responses up to 64 KiB without Set-Cookie, Vary, private/no-store/no-cache are cached. Memory has 256 entries per worker, and is not shared or persistent. Redis uses SET with EX; I/O failures bypass the cache and are logged without payloads. Provision Redis capacity/eviction/monitoring separately.

After a committed mutation, invalidate affected keys with cache.delete(key), using cache_key with the original URL/header variants, or roll a new namespace version for all variants. Schedule retries when Redis deletion returns False. Updates through other writers also need invalidation. A concurrent reader can repopulate an older value after deletion: TTL bounds this eventual consistency; use authoritative reads or versioned data keys for strict freshness. No exactly-once invalidation or stampede protection is claimed. Test workload/tenant boundaries before integration.

## API Gateway

Install requirements and run `python gateway.py` to synthesize the REST API sample into cdk.out. It uses a public MOCK GET integration so it is self-contained; replace that integration with a reviewed real backend before use. Stage caching is disabled globally and enabled only on the named GET method, encrypted, with TTL 1–3600 seconds. Query keys are declared on the method and integration. Add EVERY response-varying query/header parameter before integrating a real backend; unlisted inputs do not partition the gateway cache. HTTP API native caching is unsupported.

Deployment is separate and incurs AWS cache charges. API Gateway can cache responses independently of backend Cache-Control; do not use this sample for private responses. Plan cache flush/invalidation after writes, test cache hit/miss metrics, and configure IAM restrictions for invalidation. No deployment or live AWS validation is performed by saving/exporting in API Builder.
