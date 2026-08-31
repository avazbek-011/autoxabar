"""Payme uchun kirish nuqtalari.

  POST /api/payme     — Payme serveri chaqiradigan Merchant API (JSON-RPC)
  GET  /tolov/natija  — foydalanuvchi to'lovdan keyin qaytadigan sahifa
"""
import logging

from flask import Blueprint, jsonify, render_template, request

from core.auth import current_user
from core.db import query
from services import billing
from services.payme import MerchantAPI

log = logging.getLogger("payme.bp")

bp = Blueprint("payme", __name__)


def _on_paid(payment_id):
    billing.on_payment_paid(payment_id)


def _on_cancelled(payment_id, state):
    log.info("Payme tranzaksiya bekor qilindi: payment=%s state=%s", payment_id, state)


merchant = MerchantAPI(on_paid=_on_paid, on_cancelled=_on_cancelled)


@bp.route("/api/payme", methods=["POST"])
def merchant_endpoint():
    """Payme JSON-RPC so'rovlarini qabul qiladi.

    Diqqat: bu yo'l CSRF tekshiruvidan ozod (app.py -> CSRF_EXEMPT).
    Avtorizatsiya Basic-auth orqali kassa kaliti bilan tekshiriladi.
    """
    raw = request.get_data(as_text=True)
    auth = request.headers.get("Authorization", "")
    response = merchant.handle(auth, raw)
    return jsonify(response)


@bp.route("/tolov/natija")
def result():
    """Payme checkout'dan qaytish sahifasi."""
    payment_id = request.args.get("payment_id", type=int)
    payment = None
    if payment_id:
        payment = query("SELECT * FROM payments WHERE id = ?", (payment_id,), one=True)
        user = current_user()
        # Boshqa foydalanuvchining to'lovini ko'rsatmaymiz
        if payment and user and payment["user_id"] != user["id"] and user["role"] != "admin":
            payment = None
    return render_template("site/payment_result.html", payment=payment)
