"""App configuration — cache TTL, service metadata path."""

import os

CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "30"))

SERVICES_CONFIG_PATH = os.environ.get("SERVICES_CONFIG_PATH", "/config/services.yaml")
