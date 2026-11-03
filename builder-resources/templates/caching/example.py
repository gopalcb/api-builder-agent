"""Run an isolated public sample route to demonstrate cache hits without deployment."""

import json
import os
from pathlib import Path
import time

from flask import Flask

from route_cache import MemoryCache, cached_response

policy = json.loads((Path(__file__).parent / "cache-policy.json").read_text())
app = Flask(__name__)
cache = MemoryCache()

if policy["kind"] == "redis":
    # Redis is an optional adapter and is installed only for the Redis template.
    from redis_cache import RedisCache
    cache = RedisCache(os.environ["REDIS_URL"])


@app.get(policy["path"])
@cached_response(policy, cache)
def public_sample() -> dict:
    """Return a timestamp that stays fixed while the public response is cached."""
    return {"message": "Public cache sample", "generated_at": time.time()}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5055)
