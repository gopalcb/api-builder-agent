"""Adapt Redis to the public-response cache protocol with bounded I/O timeouts."""

import json
import logging

import redis


class RedisCache:
    """Use Redis expiry and fall back to authoritative reads during cache outages."""

    def __init__(self, url: str) -> None:
        """Connect using a runtime secret, never an exported credential."""
        self.client = redis.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1, decode_responses=True)

    def execute(self, operation: str, *args, **kwargs):
        """Translate Redis outages once without logging credentials or payloads."""
        try:
            return getattr(self.client, operation)(*args, **kwargs)
        except redis.RedisError:
            logging.getLogger(__name__).warning("Cache unavailable during %s; use authoritative source", operation)
            return None

    def get(self, key: str) -> dict | None:
        """Read a JSON response previously stored by this adapter."""
        value = self.execute("get", key)

        return json.loads(value) if value is not None else None

    def set(self, key: str, value: dict, ttl: int) -> None:
        """Set payload and expiry atomically."""
        self.execute("set", key, json.dumps(value), ex=ttl)

    def delete(self, key: str) -> bool:
        """Report invalidation failure so a durable worker can retry it."""
        return self.execute("delete", key) is not None
