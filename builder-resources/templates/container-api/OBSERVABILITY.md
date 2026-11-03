# Local tracing

Saved Observability & Tracing settings are included in builder-configuration.json.
When enabled, every API request creates an OpenTelemetry server span with W3C
traceparent propagation, route template, status and duration. Health requests may
be excluded. Request bodies, query strings, credentials and headers are not captured.
Existing JSON logs include the active trace ID. Metrics and log export are not enabled.

Run `docker compose up --build -d`. Jaeger is included and the API exports via
`http://jaeger:4318/v1/traces` inside the Compose network. Open
http://127.0.0.1:16686 and select the configured service name with `-api` appended.
If the builder's Jaeger is already running, use
`API_PORT=8082 JAEGER_UI_PORT=16687 docker compose up --build -d` and open port 16687 instead.
Collector data is transient and lost on restart. Ports bind only to loopback.

For a host Python process, the saved local endpoint is used. Override it with
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT when needed. Settings are read on startup;
rebuild/restart after configuration changes. A sampling ratio of 1 records all
new root traces, 0 records none; parent sampling decisions are respected.
Collector outages never change API responses; queued spans can be lost.
Use X-Trace-ID to correlate a response with Jaeger. Generate a configured API
request (health is excluded by default), then allow a moment for batch export.
