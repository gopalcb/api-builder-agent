# Local OpenTelemetry integration

Research date: 2026-11-02. Sources:
- https://opentelemetry.io/docs/languages/python/exporters/
- https://www.jaegertracing.io/docs/2.22/getting-started/

Use the SDK OTLP HTTP protobuf exporter, explicit /v1/traces URL, a batch span
processor, parent-based ratio sampling and service resources. Jaeger 2.22.0 is a
local receiver/viewer with transient memory storage. It receives host traffic on
4318 and exposes the UI on 16686. Docker applications use the jaeger Compose
service name; localhost inside the API container is not the host collector.

The tested source of truth is builder-agents/shared/telemetry_service.py.
project_build_service copies this runtime and the saved project policy into every
container artifact. Agents generating an API must preserve this integration,
requirements, compose.yaml and OBSERVABILITY.md rather than synthesize a second
telemetry implementation. Never claim configured tracing is exporting until an
actual request has been retrieved from the collector. Do not include private
request values in attributes. Metrics, log export, cloud and browser tracing are
outside this localhost trace implementation.
