"""App configuration — cache TTL, service metadata path."""

import os

CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "30"))

K8S_TIMEOUT_SECONDS = int(os.environ.get("K8S_TIMEOUT_SECONDS", "3"))
