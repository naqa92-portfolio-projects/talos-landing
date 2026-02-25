from flask import Blueprint, render_template

from app.k8s import get_cluster_stats, get_infra_apps, get_services

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return render_template(
        "index.html",
        stats=get_cluster_stats(),
        infra_apps=get_infra_apps(),
        services=get_services(),
    )


@bp.route("/partials/cluster-stats")
def partial_cluster_stats():
    return render_template("partials/cluster_stats.html", stats=get_cluster_stats())


@bp.route("/partials/infra-cards")
def partial_infra_cards():
    return render_template("partials/infra_cards.html", infra_apps=get_infra_apps())


@bp.route("/partials/service-cards")
def partial_service_cards():
    return render_template("partials/service_cards.html", services=get_services())


@bp.route("/healthz")
def healthz():
    return "ok"
