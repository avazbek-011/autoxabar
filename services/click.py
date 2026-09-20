"""Click (click.uz) integratsiyasi — SHOP API.

Click serveri bizga ikki bosqichda so'rov yuboradi:

    1) Prepare  (action = 0)  — buyurtmani tekshirish va band qilish
    2) Complete (action = 1)  — pul yechildi, xizmatni faollashtirish

So'rov `application/x-www-form-urlencoded` ko'rinishida keladi, javob esa
JSON bo'lishi shart. Haqiqiylik `sign_string` (MD5) orqali tekshiriladi.

Buyurtma raqami sifatida `payments.id` ishlatiladi — Click uni
`merchant_trans_id` maydonida yuboradi.

Hujjat: https://docs.click.uz/shop-api/requests
"""
import hashlib
import hmac
import logging
import sqlite3
from urllib.parse import urlencode

from config import config
from core.db import execute, now_str, query, update

log = logging.getLogger("click")

# ---- Bosqichlar ----
ACTION_PREPARE = 0
ACTION_COMPLETE = 1

# ---- Tranzaksiya holatlari (click_transactions.state) ----
STATE_WAITING = 0      # Prepare o'tdi, Complete kutilmoqda
STATE_PAID = 1         # Complete o'tdi, pul hisobga tushdi
STATE_CANCELLED = -1   # bekor qilingan

# ---- Click kutadigan xatolik kodlari ----
ERR_OK = 0
ERR_SIGN = -1
ERR_AMOUNT = -2
ERR_ACTION = -3
ERR_ALREADY_PAID = -4
ERR_NO_ORDER = -5
ERR_NO_TRANSACTION = -6
ERR_UPDATE_FAILED = -7
ERR_BAD_REQUEST = -8
ERR_CANCELLED = -9

# Matnlar Click hujjatidagi bilan aynan bir xil bo'lishi kerak
NOTES = {
    ERR_OK: "Success",
    ERR_SIGN: "SIGN CHECK FAILED!",
    ERR_AMOUNT: "Incorrect parameter amount",
    ERR_ACTION: "Action not found",
    ERR_ALREADY_PAID: "Already paid",
    ERR_NO_ORDER: "User does not exist",
    ERR_NO_TRANSACTION: "Transaction does not exist",
    ERR_UPDATE_FAILED: "Failed to update user",
    ERR_BAD_REQUEST: "Error in request from click",
    ERR_CANCELLED: "Transaction cancelled",
}


def configured():
    """Click bilan ishlash uchun barcha kalitlar bormi?"""
    return bool(
        config.CLICK_MERCHANT_ID and config.CLICK_SERVICE_ID and config.CLICK_SECRET_KEY
    )


def _float(value, default=0.0):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _int(value, default=0):
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def reply(params, code, extra=None):
    """Click kutgan JSON javobni tuzadi."""
    out = {
        "click_trans_id": _int(params.get("click_trans_id")),
        "merchant_trans_id": str(params.get("merchant_trans_id") or ""),
        "error": code,
        "error_note": NOTES.get(code, "Error"),
    }
    if extra:
        out.update(extra)
    return out


# =====================================================================
#  SHOP API  —  Click -> biz
# =====================================================================
class ShopAPI:
    """Prepare / Complete so'rovlarini qayta ishlaydi."""

    def __init__(self, on_paid=None, on_cancelled=None):
        self.on_paid = on_paid
        self.on_cancelled = on_cancelled

    @property
    def configured(self):
        return configured()

    # ---------------------------------------------------------- imzo
    @staticmethod
    def _sign_source(params, action):
        """MD5 uchun manba satri.

        Prepare  : click_trans_id + service_id + SECRET_KEY + merchant_trans_id
                   + amount + action + sign_time
        Complete : ... + merchant_trans_id + merchant_prepare_id + amount + ...
        """
        parts = [
            params.get("click_trans_id", ""),
            params.get("service_id", ""),
            config.CLICK_SECRET_KEY,
            params.get("merchant_trans_id", ""),
        ]
        if action == ACTION_COMPLETE:
            parts.append(params.get("merchant_prepare_id", ""))
        parts += [
            params.get("amount", ""),
            params.get("action", ""),
            params.get("sign_time", ""),
        ]
        return "".join(str(p) for p in parts)

    def check_sign(self, params, action):
        """Imzoni tekshiradi.

        Diqqat: qiymatlar Click yuborgan AYNAN shaklda hash qilinadi.
        `amount` ni float'ga o'girib qayta formatlash imzoni buzadi.
        """
        if not self.configured:
            # Kalit yo'q bo'lsa hech qanday imzo to'g'ri deb topilmasligi kerak
            return False
        given = str(params.get("sign_string") or "").strip().lower()
        if len(given) != 32:
            return False
        mine = hashlib.md5(
            self._sign_source(params, action).encode("utf-8")
        ).hexdigest()
        return hmac.compare_digest(mine, given)

    # ---------------------------------------------------------- yordamchilar
    @staticmethod
    def _payment(params):
        try:
            payment_id = int(str(params.get("merchant_trans_id") or "").strip())
        except (TypeError, ValueError):
            return None
        return query("SELECT * FROM payments WHERE id = ?", (payment_id,), one=True)

    @staticmethod
    def _tx(click_trans_id):
        return query(
            "SELECT * FROM click_transactions WHERE click_trans_id = ?",
            (str(click_trans_id),),
            one=True,
        )

    _reply = staticmethod(reply)

    def _cancel(self, tx, payment, note=""):
        """Tranzaksiyani va to'lovni bekor qilingan deb belgilaydi."""
        if tx and tx["state"] != STATE_CANCELLED:
            update(
                "click_transactions",
                {
                    "state": STATE_CANCELLED,
                    "error_note": note or "cancelled by click",
                    "cancel_time": now_str(),
                    "updated_at": now_str(),
                },
                "id = ?",
                (tx["id"],),
            )
        if payment and payment["status"] != "cancelled":
            update(
                "payments",
                {"status": "cancelled", "updated_at": now_str()},
                "id = ?",
                (payment["id"],),
            )
        if self.on_cancelled and payment:
            try:
                self.on_cancelled(payment["id"], note)
            except Exception:
                log.exception("on_cancelled callback xatosi (payment %s)", payment["id"])

    def _guard(self, params, action):
        """Ikkala bosqich uchun umumiy tekshiruvlar. Xato bo'lsa kodni qaytaradi."""
        if not self.configured:
            log.error("Click kalitlari sozlanmagan — so'rov rad etildi")
            return ERR_BAD_REQUEST
        if _int(params.get("action"), -1) != action:
            return ERR_ACTION
        if not self.check_sign(params, action):
            log.warning(
                "Click imzosi mos kelmadi: trans=%s action=%s",
                params.get("click_trans_id"),
                action,
            )
            return ERR_SIGN
        if str(params.get("service_id") or "") != str(config.CLICK_SERVICE_ID):
            return ERR_BAD_REQUEST
        if not str(params.get("click_trans_id") or "").strip():
            return ERR_BAD_REQUEST
        return None

    # ---------------------------------------------------------- Prepare
    def prepare(self, params):
        """action = 0 — buyurtmani tekshiramiz va tranzaksiya ochamiz."""
        bad = self._guard(params, ACTION_PREPARE)
        if bad is not None:
            return self._reply(params, bad)

        click_trans_id = str(params.get("click_trans_id")).strip()
        payment = self._payment(params)
        if not payment:
            return self._reply(params, ERR_NO_ORDER)

        tx = self._tx(click_trans_id)

        # Click o'zi xatolik bilan kelgan bo'lsa — to'lovni bekor qilamiz
        if _float(params.get("error"), 0) < 0:
            self._cancel(tx, payment, note=str(params.get("error_note") or ""))
            return self._reply(params, ERR_CANCELLED)

        if payment["status"] == "paid":
            return self._reply(params, ERR_ALREADY_PAID)
        if payment["status"] == "cancelled":
            return self._reply(params, ERR_CANCELLED)

        if abs(_float(params.get("amount")) - float(payment["amount"])) > 0.01:
            log.warning(
                "Click summasi mos emas: kutilgan=%s kelgan=%s (payment %s)",
                payment["amount"],
                params.get("amount"),
                payment["id"],
            )
            return self._reply(params, ERR_AMOUNT)

        if tx:
            # Takroriy Prepare — o'sha merchant_prepare_id qaytariladi
            if tx["state"] == STATE_PAID:
                return self._reply(params, ERR_ALREADY_PAID)
            if tx["state"] == STATE_CANCELLED:
                return self._reply(params, ERR_CANCELLED)
            prepare_id = tx["id"]
        else:
            try:
                prepare_id = execute(
                    "INSERT INTO click_transactions(click_trans_id, click_paydoc_id, "
                    "payment_id, amount, state, sign_time, prepare_time, created_at, "
                    "updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        click_trans_id,
                        str(params.get("click_paydoc_id") or ""),
                        payment["id"],
                        int(payment["amount"]),
                        STATE_WAITING,
                        str(params.get("sign_time") or ""),
                        now_str(),
                        now_str(),
                        now_str(),
                    ),
                )
            except sqlite3.IntegrityError:
                # Bir vaqtda ikkita Prepare kelgan — mavjudini olamiz
                tx = self._tx(click_trans_id)
                if not tx:
                    return self._reply(params, ERR_UPDATE_FAILED)
                prepare_id = tx["id"]

        return self._reply(params, ERR_OK, {"merchant_prepare_id": int(prepare_id)})

    # ---------------------------------------------------------- Complete
    def complete(self, params):
        """action = 1 — pul yechildi, obunani faollashtiramiz."""
        bad = self._guard(params, ACTION_COMPLETE)
        if bad is not None:
            return self._reply(params, bad)

        click_trans_id = str(params.get("click_trans_id")).strip()
        tx = self._tx(click_trans_id)
        if not tx:
            return self._reply(params, ERR_NO_TRANSACTION)
        if _int(params.get("merchant_prepare_id"), -1) != int(tx["id"]):
            return self._reply(params, ERR_NO_TRANSACTION)

        payment = query(
            "SELECT * FROM payments WHERE id = ?", (tx["payment_id"],), one=True
        )
        if not payment:
            return self._reply(params, ERR_NO_ORDER)

        # Click xatolik yubordi — hujjat bo'yicha to'lovni bekor qilib -9 qaytaramiz
        if _float(params.get("error"), 0) < 0:
            log.warning(
                "Click Complete xatolik bilan keldi: %s %s (payment %s)",
                params.get("error"),
                params.get("error_note"),
                payment["id"],
            )
            self._cancel(tx, payment, note=str(params.get("error_note") or ""))
            return self._reply(params, ERR_CANCELLED)

        if tx["state"] == STATE_PAID:
            return self._reply(params, ERR_ALREADY_PAID)
        if tx["state"] == STATE_CANCELLED:
            return self._reply(params, ERR_CANCELLED)

        if abs(_float(params.get("amount")) - float(payment["amount"])) > 0.01:
            return self._reply(params, ERR_AMOUNT)

        paydoc = str(params.get("click_paydoc_id") or "") or tx["click_paydoc_id"]
        update(
            "click_transactions",
            {
                "state": STATE_PAID,
                "click_paydoc_id": paydoc,
                "perform_time": now_str(),
                "updated_at": now_str(),
            },
            "id = ?",
            (tx["id"],),
        )
        update(
            "payments",
            {
                "status": "paid",
                "paid_at": now_str(),
                "external_id": paydoc or click_trans_id,
                "updated_at": now_str(),
            },
            "id = ?",
            (payment["id"],),
        )

        # Pul allaqachon yechilgan — bu yerdagi xato Click'ga qaytarilmaydi,
        # aks holda Click to'lovni qo'lda tekshiruvga yuboradi.
        if self.on_paid:
            try:
                self.on_paid(payment["id"])
            except Exception:
                log.exception(
                    "on_paid callback xatosi (payment %s) — Complete'ga 'success' "
                    "qaytarildi, obunani qo'lda tekshiring",
                    payment["id"],
                )

        return self._reply(params, ERR_OK, {"merchant_confirm_id": int(tx["id"])})


# =====================================================================
#  To'lov havolasi
# =====================================================================
def checkout_url(payment_id, amount_soum, return_url="", card_type=""):
    """Click to'lov sahifasiga yo'naltirish havolasi.

    `transaction_param` — bizning `payments.id`; Click uni keyin
    `merchant_trans_id` sifatida qaytaradi.
    """
    if not (config.CLICK_MERCHANT_ID and config.CLICK_SERVICE_ID):
        return ""
    params = {
        "service_id": config.CLICK_SERVICE_ID,
        "merchant_id": config.CLICK_MERCHANT_ID,
        "amount": "{:.2f}".format(float(amount_soum)),
        "transaction_param": str(payment_id),
    }
    if config.CLICK_MERCHANT_USER_ID:
        params["merchant_user_id"] = config.CLICK_MERCHANT_USER_ID
    if return_url:
        params["return_url"] = return_url
    if card_type:
        params["card_type"] = card_type
    return "{}/?{}".format(config.CLICK_CHECKOUT_URL, urlencode(params))
