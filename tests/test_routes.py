from unittest.mock import patch

import pytest

from app import create_app

FAKE_STATS = {
    "uptime": "10d 5h",
    "nodes_ready": 3,
    "nodes_total": 3,
    "status": "ONLINE",
    "cpu_percent": 42.0,
    "ram_percent": 61.3,
}

FAKE_INFRA = [
    {"name": "cert-manager", "health": "Healthy", "sync": "Synced"},
]

FAKE_SERVICES = [
    {
        "name": "gitea",
        "icon": "git-branch",
        "url": "https://git.example.com",
        "name_fr": "Gitea",
        "name_en": "Gitea",
        "desc_fr": "Forge Git",
        "desc_en": "Git forge",
        "health": "Healthy",
        "sync": "Synced",
    },
]


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@patch("app.routes.get_services", return_value=FAKE_SERVICES)
@patch("app.routes.get_infra_apps", return_value=FAKE_INFRA)
@patch("app.routes.get_cluster_stats", return_value=FAKE_STATS)
def test_index(mock_stats, mock_infra, mock_services, client):
    resp = client.get("/")
    assert resp.status_code == 200


@patch("app.routes.get_cluster_stats", return_value=FAKE_STATS)
def test_partial_cluster_stats(mock_stats, client):
    resp = client.get("/partials/cluster-stats")
    assert resp.status_code == 200


@patch("app.routes.get_infra_apps", return_value=FAKE_INFRA)
def test_partial_infra_cards(mock_infra, client):
    resp = client.get("/partials/infra-cards")
    assert resp.status_code == 200


@patch("app.routes.get_services", return_value=FAKE_SERVICES)
def test_partial_service_cards(mock_services, client):
    resp = client.get("/partials/service-cards")
    assert resp.status_code == 200


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.data == b"ok"
