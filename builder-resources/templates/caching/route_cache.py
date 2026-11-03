"""Cache explicitly public Flask GET responses with bounded memory and expiry."""

from collections import OrderedDict
from functools import wraps
from hashlib import sha256
import json
from threading import RLock
import time

from flask import make_response, request


class MemoryCache:
    """Store a bounded number of responses in one worker process."""

    def __init__(self, capacity: int = 256) -> None:
        """Initialize a process-local cache and synchronization lock."""
        self.entries = OrderedDict()
        self.capacity = capacity
        self.lock = RLock()

    def get(self, key: str) -> dict | None:
        """Return a live value, dropping an expired entry."""
        with self.lock:
            entry = self.entries.get(key)

            if entry is None:
                return None

            if entry[0] <= time.monotonic():
                del self.entries[key]
                return None

            self.entries.move_to_end(key)
            return entry[1]

    def set(self, key: str, value: dict, ttl: int) -> None:
        """Store a value with expiry and evict oldest entries at capacity."""
        with self.lock:
            self.entries[key] = (time.monotonic() + ttl, value)
            self.entries.move_to_end(key)

            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)

    def delete(self, key: str) -> None:
        """Invalidate one key after a successful primary write."""
        with self.lock:
            self.entries.pop(key, None)


def cache_key(policy: dict, path: str, query: str, headers: list) -> str:
    """Partition by project revision, exact URL and request header variants."""
    material = json.dumps([path, query, sorted(headers)], separators=(",", ":"))

    return policy["namespace"] + ":" + sha256(material.encode()).hexdigest()


def cached_response(policy: dict, cache: object):
    """Wrap a public handler; bypass identity-bearing or uncacheable responses."""
    def decorate(handler):
        """Bind a reviewed policy to an existing Flask route handler."""
        @wraps(handler)
        def wrapped(*args, **kwargs):
            """Serve a live cache entry or execute the authoritative handler."""
            if request.method != "GET" or request.path != policy["path"] or request.headers.get("Authorization") or request.headers.get("Cookie") or request.cache_control.no_cache or request.cache_control.no_store:
                return handler(*args, **kwargs)

            key = cache_key(policy, request.path, request.query_string.decode("latin1"), list(request.headers.items()))
            hit = cache.get(key)

            if hit is not None:
                response = make_response(bytes.fromhex(hit["body"]), 200)
                response.headers.clear()
                response.headers.update(hit["headers"])
                response.headers["X-Cache"] = "HIT"
                return response

            response = make_response(handler(*args, **kwargs))
            control = response.headers.get("Cache-Control", "").lower()
            eligible = response.status_code == 200 and not response.is_streamed and not response.headers.get("Set-Cookie") and not response.headers.get("Vary") and not any(token in control for token in ("private", "no-store", "no-cache"))

            if eligible:
                body = response.get_data()

                if len(body) <= 65536:
                    ttl = min([policy["ttl_seconds"], *[value for value in (response.cache_control.max_age, response.cache_control.s_maxage) if value is not None]])

                    if ttl > 0:
                        cache.set(key, {"body": body.hex(), "headers": list(response.headers.items())}, ttl)

            response.headers["X-Cache"] = "MISS"
            return response

        return wrapped

    return decorate
