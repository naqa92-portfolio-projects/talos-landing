"""Kubernetes API client — nodes, metrics, ArgoCD applications."""

import time
from typing import Any

from kubernetes import client, config as k8s_config

from app.config import CACHE_TTL_SECONDS, K8S_TIMEOUT_SECONDS

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
    return _cached("cluster_stats", _fetch_cluster_stats)


def get_infra_apps() -> list[dict]:
    return _cached("infra_apps", _fetch_infra_apps)


def get_services() -> list[dict]:
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
    except Exception:
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
    except Exception:
        pass

    return {
        "uptime": uptime,
        "nodes_ready": nodes_ready,
        "nodes_total": nodes_total,
        "status": status,
        "cpu_percent": cpu_percent,
        "ram_percent": ram_percent,
    }


def _fetch_infra_apps() -> list[dict]:
    clients = _get_clients()
    custom: client.CustomObjectsApi = clients["custom"]

    try:
        apps = custom.list_namespaced_custom_object(
            "argoproj.io",
            "v1alpha1",
            "argocd",
            "applications",
            _request_timeout=K8S_TIMEOUT_SECONDS,
        )
    except Exception:
        return []

    result = []
    for app in apps.get("items", []):
        spec = app.get("spec", {})
        if spec.get("project") != "infra":
            continue
        st = app.get("status", {})
        result.append(
            {
                "name": app["metadata"]["name"],
                "health": st.get("health", {}).get("status", "Unknown"),
                "sync": st.get("sync", {}).get("status", "Unknown"),
            }
        )
    return result


def _fetch_services() -> list[dict]:
    clients = _get_clients()
    custom: client.CustomObjectsApi = clients["custom"]

    try:
        routes = custom.list_cluster_custom_object(
            "gateway.networking.k8s.io",
            "v1",
            "httproutes",
            _request_timeout=K8S_TIMEOUT_SECONDS,
        )
    except Exception:
        return []

    try:
        apps = custom.list_namespaced_custom_object(
            "argoproj.io",
            "v1alpha1",
            "argocd",
            "applications",
            _request_timeout=K8S_TIMEOUT_SECONDS,
        )
        apps_by_name = {a["metadata"]["name"]: a for a in apps.get("items", [])}
    except Exception:
        apps_by_name = {}

    result = []
    for route in routes.get("items", []):
        annotations = route.get("metadata", {}).get("annotations", {})
        if annotations.get("taloslab.cc/visible") != "true":
            continue
        if annotations.get("taloslab.cc/name") == "landing-page":
            continue

        hostnames = route.get("spec", {}).get("hostnames", [])
        url = f"https://{hostnames[0]}" if hostnames else ""

        argocd_key = annotations.get(
            "taloslab.cc/argocd-app",
            route["metadata"].get("namespace", ""),
        )
        app = apps_by_name.get(argocd_key, {})
        st = app.get("status", {})

        result.append(
            {
                "name": annotations.get(
                    "taloslab.cc/name", route["metadata"].get("name", "")
                ),
                "desc": annotations.get("taloslab.cc/desc", ""),
                "icon": annotations.get("taloslab.cc/icon", "box"),
                "url": url,
                "health": st.get("health", {}).get("status", "Unknown"),
                "sync": st.get("sync", {}).get("status", "Unknown"),
            }
        )
    return result
