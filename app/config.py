"""App configuration — cache TTL, service metadata path."""

import os
from pathlib import Path

CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "30"))

_default_config = "/config/services.yaml"
_local_config = Path(__file__).resolve().parent.parent / "config" / "services.yaml"
if not Path(_default_config).exists() and _local_config.exists():
    _default_config = str(_local_config)

SERVICES_CONFIG_PATH = os.environ.get("SERVICES_CONFIG_PATH", _default_config)
