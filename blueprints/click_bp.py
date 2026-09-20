"""Click uchun kirish nuqtalari (SHOP API).

Click ikki bosqichda so'rov yuboradi va ularni `action` maydoni orqali
ajratadi. Kassa sozlamasida bitta manzil ko'rsatilsa ham, alohida ikkita
manzil ko'rsatilsa ham ishlashi uchun uchala yo'l ham mavjud:

  POST /api/payments/click/webhook  — bitta manzil, action bo'yicha ajratadi
  POST /api/click/prepare           — faqat Prepare  (action = 0)
  POST /api/click/complete          — faqat Complete (action = 1)

Diqqat: bu yo'llar CSRF tekshiruvidan ozod (app.py -> CSRF_EXEMPT).
Haqiqiylik `sign_string` (MD5) orqali tekshiriladi — services/click.py.
"""
import logging

from flask import Blueprint, jsonify, request

from services import billing
from services.click import (
    ACTION_COMPLETE,
    ACTION_PREPARE,
    ERR_ACTION,
    ERR_UPDATE_FAILED,
    ShopAPI,
    reply,
    to_int,
)

log = logging.getLogger("click.bp")

bp = Blueprint("click", __name__)


def _on_paid(payment_id):
    billing.on_payment_paid(payment_id)


def _on_cancelled(payment_id, note):
    log.info("Click to'lovi bekor qilindi: payment=%s sabab=%s", payment_id, note)


shop = ShopAPI(on_paid=_on_paid, on_cancelled=_on_cancelled)


def _params():
    """So'rov tanasini lug'atga aylantiradi.

    Click `x-www-form-urlencoded` yuboradi; ba'zi test vositalari JSON
    yuborgani uchun uni ham qabul qilamiz.
    """
    data = request.form.to_dict()
    if not data:
        body = request.get_json(silent=True)
        if isinstance(body, dict):
            data = {k: v for k, v in body.items()}
    if not data:
        data = request.args.to_dict()
    return data


def _handle(stage, func, params):
    try:
        return jsonify(func(params))
    except Exception:
        # Click HTML xato sahifasini tushunmaydi — har doim JSON qaytaramiz
        log.exception("Click %s so'rovida kutilmagan xatolik", stage)
        return jsonify(reply(params, ERR_UPDATE_FAILED))


@bp.route("/api/payments/click/webhook", methods=["POST"])
def webhook():
    """Bitta manzil: Prepare va Complete `action` bo'yicha ajratiladi.

    Click kassasida Prepare URL va Complete URL sifatida aynan shu bitta
    manzilni ko'rsatish mumkin — qaysi bosqich ekanini so'rovning o'zi
    aytadi (action = 0 yoki 1).
    """
    params = _params()
    action = to_int(params.get("action"), -1)

    if action == ACTION_PREPARE:
        return _handle("Prepare", shop.prepare, params)
    if action == ACTION_COMPLETE:
        return _handle("Complete", shop.complete, params)

    log.warning("Click webhook: noma'lum action=%r", params.get("action"))
    return jsonify(reply(params, ERR_ACTION))


@bp.route("/api/click/prepare", methods=["POST"])
def prepare():
    return _handle("Prepare", shop.prepare, _params())


@bp.route("/api/click/complete", methods=["POST"])
def complete():
    return _handle("Complete", shop.complete, _params())
