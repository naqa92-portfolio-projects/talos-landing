"""Kubernetes API client — nodes, metrics, ArgoCD Applications + Crossplane XR Apps."""

import logging
import time
from typing import Any

from kubernetes import client
from kubernetes import config as k8s_config
from kubernetes.client.exceptions import ApiException
from urllib3.exceptions import HTTPError as Urllib3Error

from app import fixtures
from app.config import CACHE_TTL_SECONDS, K8S_TIMEOUT_SECONDS, MOCK_MODE

logger = logging.getLogger(__name__)

# Le dashboard doit rester affichable quand le cluster ne répond pas : erreurs HTTP de l'API
# (ApiException), coupures et timeouts réseau (urllib3), et payloads partiels côté CRD.
API_ERRORS = (ApiException, Urllib3Error)
PAYLOAD_ERRORS = (KeyError, TypeError)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, Any]] = {}


def _cached(key: str, fn):
    now = time.monotonic()
    if key in _cache and now - _cache[key][0] < CACHE_TTL_SECONDS:
        return _cache[key][1]
    result = fn()
    _cache[key] = (now, result)
    return result


# ---------------------------------------------------------------------------
# K8s clients (lazy singleton)
# ---------------------------------------------------------------------------

_clients: dict[str, Any] = {}


def _get_clients():
    if not _clients:
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            k8s_config.load_kube_config()
        _clients["core"] = client.CoreV1Api()
        _clients["custom"] = client.CustomObjectsApi()
    return _clients


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_uptime(seconds: float) -> str:
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    return f"{days}d {hours}h"


def _parse_cpu(value: str) -> float:
    """Parse CPU usage string (e.g. '250m', '1') to millicores."""
    if value.endswith("n"):
        return float(value[:-1]) / 1e6
    if value.endswith("m"):
        return float(value[:-1])
    return float(value) * 1000


def _parse_memory(value: str) -> float:
    """Parse memory string (e.g. '512Ki', '1Gi') to bytes."""
    units = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4}
    for suffix, multiplier in units.items():
        if value.endswith(suffix):
            return float(value[: -len(suffix)]) * multiplier
    # bare bytes or unknown
    return float(value)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_cluster_stats() -> dict:
    if MOCK_MODE:
        return fixtures.CLUSTER_STATS
    return _cached("cluster_stats", _fetch_cluster_stats)


def get_infra_apps() -> list[dict]:
    if MOCK_MODE:
        return fixtures.INFRA_APPS
    return _cached("infra_apps", _fetch_infra_apps)


def get_services() -> list[dict]:
    if MOCK_MODE:
        return fixtures.SERVICES
    return _cached("services", _fetch_services)


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------


def _fetch_cluster_stats() -> dict:
    clients = _get_clients()
    core: client.CoreV1Api = clients["core"]
    custom: client.CustomObjectsApi = clients["custom"]

    try:
        nodes = core.list_node(_request_timeout=K8S_TIMEOUT_SECONDS).items
    except API_ERRORS as exc:
        logger.warning("Liste des nodes indisponible: %s", exc)
        return {
            "uptime": "N/A",
            "nodes_ready": 0,
            "nodes_total": 0,
            "status": "UNKNOWN",
            "cpu_percent": None,
            "ram_percent": None,
        }

    # Uptime from oldest node
    oldest_ts = min(n.metadata.creation_timestamp for n in nodes)
    uptime_sec = time.time() - oldest_ts.timestamp()
    uptime = _format_uptime(uptime_sec)

    # Node readiness
    nodes_total = len(nodes)
    nodes_ready = 0
    for n in nodes:
        for cond in n.status.conditions or []:
            if cond.type == "Ready" and cond.status == "True":
                nodes_ready += 1
                break

    status = "ONLINE" if nodes_ready == nodes_total else "DEGRADED"

    # CPU / RAM from metrics-server
    cpu_percent = None
    ram_percent = None
    try:
        metrics = custom.list_cluster_custom_object(
            "metrics.k8s.io",
            "v1beta1",
            "nodes",
            _request_timeout=K8S_TIMEOUT_SECONDS,
        )
        total_cpu_usage = 0.0
        total_cpu_alloc = 0.0
        total_mem_usage = 0.0
        total_mem_alloc = 0.0

        metrics_by_name = {m["metadata"]["name"]: m for m in metrics["items"]}
        for n in nodes:
            name = n.metadata.name
            m = metrics_by_name.get(name)
            if not m:
                continue
            total_cpu_usage += _parse_cpu(m["usage"]["cpu"])
            total_mem_usage += _parse_memory(m["usage"]["memory"])
            total_cpu_alloc += _parse_cpu(n.status.allocatable["cpu"])
            total_mem_alloc += _parse_memory(n.status.allocatable["memory"])

        if total_cpu_alloc > 0:
            cpu_percent = round(total_cpu_usage / total_cpu_alloc * 100, 1)
        if total_mem_alloc > 0:
            ram_percent = round(total_mem_usage / total_mem_alloc * 100, 1)
    except (*API_ERRORS, *PAYLOAD_ERRORS) as exc:
        logger.info("Métriques CPU/RAM indisponibles: %s", exc)

    return {
        "uptime": uptime,
        "nodes_ready": nodes_ready,
        "nodes_total": nodes_total,
        "status": status,
        "cpu_percent": cpu_percent,
        "ram_percent": ram_percent,
    }


def _ready_condition_health(resource: dict) -> str:
    """Map a Ready condition → landing-page health label."""
    for cond in resource.get("status", {}).get("conditions", []):
        if cond.get("type") == "Ready":
            return "Healthy" if cond.get("status") == "True" else "Degraded"
    return "Unknown"


def _fetch_gitops_resources() -> dict[str, str]:
    """Return the health of every GitOps-managed unit, keyed by name.

    Unifies ArgoCD Applications (infra) and Crossplane XR Apps (business apps)
    into a single list of deployable units. The two report health differently:
    an Application carries it in status.health.status, an XR in its Ready
    condition — hence the health is resolved here rather than by the callers.
    """
    clients = _get_clients()
    custom: client.CustomObjectsApi = clients["custom"]
    result: dict[str, str] = {}

    try:
        argo_apps = custom.list_namespaced_custom_object(
            "argoproj.io",
            "v1alpha1",
            "argocd",
            "applications",
            _request_timeout=K8S_TIMEOUT_SECONDS,
        )
        for argo_app in argo_apps.get("items", []):
            health = argo_app.get("status", {}).get("health", {}).get("status")
            result[argo_app["metadata"]["name"]] = health or "Unknown"
    except (*API_ERRORS, *PAYLOAD_ERRORS) as exc:
        logger.info("Applications ArgoCD indisponibles: %s", exc)

    try:
        apps = custom.list_cluster_custom_object(
            "taloslab.cc",
            "v1alpha1",
            "apps",
            _request_timeout=K8S_TIMEOUT_SECONDS,
        )
        for app in apps.get("items", []):
            result[app["metadata"]["name"]] = _ready_condition_health(app)
    except (*API_ERRORS, *PAYLOAD_ERRORS) as exc:
        logger.info("XR Apps Crossplane indisponibles: %s", exc)

    return result


def _fetch_infra_apps() -> list[dict]:
    resources = _fetch_gitops_resources()
    return sorted(
        [{"name": name, "health": health} for name, health in resources.items()],
        key=lambda x: x["name"],
    )


def _fetch_routes() -> list[dict]:
    """Return every Gateway API route that can carry a service card."""
    clients = _get_clients()
    custom: client.CustomObjectsApi = clients["custom"]

    try:
        listed = custom.list_cluster_custom_object(
            "gateway.networking.k8s.io",
            "v1",
            "httproutes",
            _request_timeout=K8S_TIMEOUT_SECONDS,
        )
    except API_ERRORS as exc:
        logger.warning("httproutes indisponibles: %s", exc)
        return []

    return listed.get("items", [])


def _fetch_services() -> list[dict]:
    routes = _fetch_routes()
    if not routes:
        return []

    resources = _fetch_gitops_resources()

    result = []
    for route in routes:
        annotations = route.get("metadata", {}).get("annotations", {})
        if annotations.get("taloslab.cc/visible") != "true":
            continue
        if annotations.get("taloslab.cc/name") == "landing-page":
            continue

        hostnames = route.get("spec", {}).get("hostnames", [])
        url = f"https://{hostnames[0]}" if hostnames else ""

        # External services (taloslab.cc/external=true) bypass status lookup —
        # they are not deployed by GitOps.
        # Route name == resource name (Application or XR App) by convention.
        # Annotation taloslab.cc/argocd-app overrides for non-conventional cases
        # (e.g. HTTPRoute grafana → Application victoria-metrics-k8s-stack).
        if annotations.get("taloslab.cc/external") == "true":
            health = "Healthy"
        else:
            resource_key = annotations.get(
                "taloslab.cc/argocd-app",
                route["metadata"].get("name", ""),
            )
            health = resources.get(resource_key, "Unknown")

        result.append(
            {
                "name": annotations.get(
                    "taloslab.cc/name", route["metadata"].get("name", "")
                ),
                "desc": annotations.get("taloslab.cc/desc", ""),
                "icon": annotations.get("taloslab.cc/icon", "box"),
                "url": url,
                "health": health,
            }
        )
    return result
