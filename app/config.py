"""App configuration — cache TTL, service metadata path."""

import os

CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "30"))

K8S_TIMEOUT_SECONDS = int(os.environ.get("K8S_TIMEOUT_SECONDS", "3"))

# Sert app.fixtures au lieu d'interroger l'API Kubernetes. Opt-in explicite :
# un défaut implicite ferait passer un ServiceAccount cassé pour un cluster sain.
MOCK_MODE = os.environ.get("TALOS_MOCK", "").lower() in {"1", "true", "yes"}
