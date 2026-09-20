"""Click uchun kirish nuqtalari (SHOP API).

  POST /api/click/prepare   — to'lovni tekshirish va band qilish (action = 0)
  POST /api/click/complete  — to'lovni yakunlash (action = 1)

Diqqat: ikkala yo'l ham CSRF tekshiruvidan ozod (app.py -> CSRF_EXEMPT).
Haqiqiylik `sign_string` (MD5) orqali tekshiriladi — services/click.py.
"""
import logging

from flask import Blueprint, jsonify, request

from services import billing
from services.click import ERR_UPDATE_FAILED, ShopAPI, reply

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


def _handle(stage, func):
    params = _params()
    try:
        return jsonify(func(params))
    except Exception:
        # Click HTML xato sahifasini tushunmaydi — har doim JSON qaytaramiz
        log.exception("Click %s so'rovida kutilmagan xatolik", stage)
        return jsonify(reply(params, ERR_UPDATE_FAILED))


@bp.route("/api/click/prepare", methods=["POST"])
def prepare():
    return _handle("Prepare", shop.prepare)


@bp.route("/api/click/complete", methods=["POST"])
def complete():
    return _handle("Complete", shop.complete)
