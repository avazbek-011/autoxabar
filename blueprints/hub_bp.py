"""Payment Hub webhook'i.

    POST /api/payments/hub/webhook

Bu manzil hub administratoriga beriladi (to'liq HTTPS manzil, redirect'siz).
CSRF tekshiruvidan ozod (app.py -> CSRF_EXEMPT): haqiqiylik
X-Hub-Signature (HMAC-SHA256) orqali tekshiriladi — services/payment_hub.py.
"""
import logging

from flask import Blueprint, jsonify, request

from services import payment_hub

log = logging.getLogger("hub.bp")

bp = Blueprint("hub", __name__)


@bp.route("/api/payments/hub/webhook", methods=["POST"])
def webhook():
    # Imzo XOM baytlar ustidan hisoblanadi — request.json emas
    raw = request.get_data(cache=False)
    try:
        status, body = payment_hub.handle_webhook(request.headers, raw)
    except Exception:
        # 5xx — hub o'sha hodisani keyinroq qayta yuboradi
        log.exception("Hub webhook'ini qayta ishlashda xato")
        status, body = 500, {"error": "internal_error"}
    return jsonify(body), status
