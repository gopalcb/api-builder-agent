---
name: cache-planning
description: Propose and review caching policies for API Builder routes using route access, freshness, tenant isolation and invalidation requirements. Use for cache design rather than general infrastructure generation.
---

Read ../../research/caching-infrastructure.md. Import authoritative routes/access policies. Default private/authenticated responses to no shared caching; never infer public access from GET alone.
Propose layer, cache key inputs, TTL, stale policy, tenant scope, invalidation triggers, version and rationale per route. Mark missing workload evidence as requirements. HTTP API has no native response cache; do not emit REST stage-cache settings for it. Keep authorization decision caching separate.
Validate once using the shared response validator; deterministic backend rules must reject private shared-cache proposals and unsupported combinations. Test cross-user isolation, expiration, mutation invalidation, cache outage and policy revision conflicts. Return a proposal, not a claim of a live cache. Use ../project-code-style/SKILL.md for implementation.
