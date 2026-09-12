"""Données statiques servies quand TALOS_MOCK=1 — développement UI sans cluster.

Mêmes formes que les retours de app.k8s : tout changement de schéma côté k8s
doit être répercuté ici, sinon les templates divergent du rendu de production.
"""

CLUSTER_STATS = {
    "uptime": "127d 8h",
    "nodes_ready": 3,
    "nodes_total": 3,
    "status": "ONLINE",
    "cpu_percent": 34.2,
    "ram_percent": 61.8,
}

INFRA_APPS = [
    {"name": "argo-cd", "health": "Healthy"},
    {"name": "cert-manager", "health": "Healthy"},
    {"name": "cilium", "health": "Healthy"},
    {"name": "cloudnative-pg", "health": "Healthy"},
    {"name": "crossplane", "health": "Healthy"},
    {"name": "external-secrets", "health": "Healthy"},
    {"name": "gateway-api", "health": "Healthy"},
    {"name": "metrics-server", "health": "Degraded"},
    {"name": "velero", "health": "Healthy"},
    {"name": "victoria-metrics-k8s-stack", "health": "Unknown"},
]

SERVICES = [
    {
        "name": "Grafana",
        "desc": "Dashboards et alerting du cluster",
        "icon": "chart-line",
        "url": "https://grafana.taloslab.cc",
        "health": "Healthy",
    },
    {
        "name": "ArgoCD",
        "desc": "État de la réconciliation GitOps",
        "icon": "git-branch",
        "url": "https://argocd.taloslab.cc",
        "health": "Healthy",
    },
    {
        "name": "Backstage",
        "desc": "Portail développeur et catalogue de services",
        "icon": "layout-dashboard",
        "url": "https://backstage.taloslab.cc",
        "health": "Healthy",
    },
    {
        "name": "Hubble",
        "desc": "Observabilité réseau eBPF",
        "icon": "radar",
        "url": "https://hubble.taloslab.cc",
        "health": "Degraded",
    },
]
