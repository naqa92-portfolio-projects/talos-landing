"""Kubernetes API client — nodes, metrics, ArgoCD applications."""

import time
from typing import Any

import yaml
from kubernetes import client, config as k8s_config

from app.config import CACHE_TTL_SECONDS, SERVICES_CONFIG_PATH

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
# services.yaml (loaded once)
# ---------------------------------------------------------------------------

_services_meta: dict | None = None


def _load_services_meta() -> dict:
    global _services_meta
    if _services_meta is None:
        try:
            with open(SERVICES_CONFIG_PATH) as f:
                data = yaml.safe_load(f)
            _services_meta = data.get("services", {})
        except Exception:
            _services_meta = {}
    return _services_meta


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
        nodes = core.list_node().items
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
    oldest_ts = min(
        n.metadata.creation_timestamp for n in nodes
    )
    uptime_sec = (time.time() - oldest_ts.timestamp())
    uptime = _format_uptime(uptime_sec)

    # Node readiness
    nodes_total = len(nodes)
    nodes_ready = 0
    for n in nodes:
        for cond in (n.status.conditions or []):
            if cond.type == "Ready" and cond.status == "True":
                nodes_ready += 1
                break

    status = "ONLINE" if nodes_ready == nodes_total else "DEGRADED"

    # CPU / RAM from metrics-server
    cpu_percent = None
    ram_percent = None
    try:
        metrics = custom.list_cluster_custom_object(
            "metrics.k8s.io", "v1beta1", "nodes"
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
            "argoproj.io", "v1alpha1", "argocd", "applications"
        )
    except Exception:
        return []

    result = []
    for app in apps.get("items", []):
        spec = app.get("spec", {})
        if spec.get("project") != "infra":
            continue
        st = app.get("status", {})
        result.append({
            "name": app["metadata"]["name"],
            "health": st.get("health", {}).get("status", "Unknown"),
            "sync": st.get("sync", {}).get("status", "Unknown"),
        })
    return result


def _fetch_services() -> list[dict]:
    clients = _get_clients()
    custom: client.CustomObjectsApi = clients["custom"]
    meta = _load_services_meta()

    if not meta:
        return []

    try:
        apps = custom.list_namespaced_custom_object(
            "argoproj.io", "v1alpha1", "argocd", "applications"
        )
    except Exception:
        return []

    result = []
    for app in apps.get("items", []):
        name = app["metadata"]["name"]
        if name not in meta:
            continue
        info = meta[name]
        st = app.get("status", {})
        result.append({
            "name": name,
            "icon": info.get("icon", "box"),
            "url": info.get("url", ""),
            "name_fr": info.get("name_fr", name),
            "name_en": info.get("name_en", name),
            "desc_fr": info.get("desc_fr", ""),
            "desc_en": info.get("desc_en", ""),
            "health": st.get("health", {}).get("status", "Unknown"),
            "sync": st.get("sync", {}).get("status", "Unknown"),
        })
    return result
