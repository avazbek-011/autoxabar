"""Payme uchun kirish nuqtasi (hozircha ishlatilmaydi — kalitlar bo'sh).

  POST /api/payme  — Payme serveri chaqiradigan Merchant API (JSON-RPC)

To'lovdan qaytish sahifasi provayderga bog'liq emas: blueprints/site.py ->
`site.payment_result` (/tolov/natija).
"""
import logging

from flask import Blueprint, jsonify, request

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

