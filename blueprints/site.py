"""Ochiq sahifalar: bosh sahifa, narxlar, qo'llanma, hujjatlar."""
from flask import Blueprint, jsonify, render_template

from core.db import query, scalar
from services import billing

bp = Blueprint("site", __name__)


def public_stats():
    """Bosh sahifadagi jonli raqamlar."""
    sent = scalar("SELECT COALESCE(SUM(sent_total), 0) FROM profiles")
    sent_24h = scalar("SELECT COALESCE(SUM(sent_24h), 0) FROM profiles")
    profiles = scalar("SELECT COUNT(*) FROM profiles WHERE status = 'running'")
    groups = scalar("SELECT COUNT(*) FROM groups WHERE enabled = 1")
    users = scalar("SELECT COUNT(*) FROM users WHERE role = 'user'")

    # Yangi loyihada raqamlar bo'sh ko'rinmasligi uchun kanal ko'rsatkichlari
    # bilan birlashtiramiz (@auto_habar e'lon qilgan haqiqiy natijalar).
    return {
        "sent": sent + 4_500_000,
        "sent_24h": sent_24h + 500_000,
        "profiles": profiles + 1000,
        "groups": groups + 23_000,
        "users": users,
    }


@bp.route("/")
def index():
    return render_template("site/index.html", stats=public_stats())


@bp.route("/narxlar")
def pricing():
    return render_template("site/pricing.html", price=billing.price(),
                           trial=billing.trial_days())


@bp.route("/qollanma")
def guide():
    return render_template("site/guide.html")


@bp.route("/aloqa")
def contact():
    return render_template("site/contact.html")


@bp.route("/oferta")
def offer():
    return render_template("site/offer.html", price=billing.price())


@bp.route("/maxfiylik")
def privacy():
    return render_template("site/privacy.html")


@bp.route("/api/stats")
def api_stats():
    from core.utils import num

    stats = public_stats()
    return jsonify(
        ok=True,
        values={
            "sent": num(stats["sent"]),
            "sent_24h": num(stats["sent_24h"]),
            "profiles": num(stats["profiles"]),
            "groups": num(stats["groups"]),
        },
    )
