"""Ochiq sahifalar: bosh sahifa, narxlar, qo'llanma, hujjatlar."""
from flask import Blueprint, jsonify, render_template, request, url_for

from core.auth import current_user
from core.db import query, scalar
from services import billing, payment_hub

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


# Natija sahifasi to'lov "kutilmoqda" bo'lsa o'zini shuncha marta yangilaydi
RESULT_REFRESHES = 24   # x 5 soniya = 2 daqiqa


@bp.route("/tolov/natija")
def payment_result():
    """To'lovdan qaytish sahifasi (Payment Hub `return_url`).

    Bu yerga qaytish "to'landi" degani EMAS — mijoz to'lamasdan ham qaytishi
    mumkin. Holat faqat webhook'dan yoki hub'dan so'rab olinadi.
    """
    payment_id = request.args.get("payment_id", type=int)
    attempt = request.args.get("n", 0, type=int)
    payment = None
    if payment_id:
        payment = query("SELECT * FROM payments WHERE id = ?", (payment_id,), one=True)
        user = current_user()
        # Boshqa foydalanuvchining to'lovini ko'rsatmaymiz
        if payment and user and payment["user_id"] != user["id"] and user["role"] != "admin":
            payment = None
        elif payment and not user:
            payment = None

    if payment and payment["status"] == "pending":
        # Webhook hali kelmagan bo'lishi mumkin — holatni hub'dan so'raymiz
        payment_hub.refresh(payment["id"])
        payment = query("SELECT * FROM payments WHERE id = ?", (payment["id"],), one=True)

    next_url = None
    if payment and payment["status"] == "pending" and attempt < RESULT_REFRESHES:
        next_url = url_for("site.payment_result", payment_id=payment["id"], n=attempt + 1)
    return render_template("site/payment_result.html", payment=payment, next_url=next_url)


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
