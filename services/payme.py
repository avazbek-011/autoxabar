"""Payme integratsiyasi.

Ikki qism:
  1) MerchantAPI  — Payme serveri bizga JSON-RPC so'rov yuboradi (to'lovni qabul qilish).
  2) SubscribeAPI — biz Payme'ga so'rov yuboramiz (karta tokeni + avto-to'lov).
"""
import base64
import binascii
import json
import logging

import requests

from config import config
from core.db import get_setting, now_str, query, execute, update

log = logging.getLogger("payme")

# ---- Pul birligi: 1 so'm = 100 tiyin ----
TIYIN = 100


def to_tiyin(soum):
    return int(round(float(soum) * TIYIN))


def to_soum(tiyin):
    return int(round(float(tiyin) / TIYIN))


# ---- Tranzaksiya holatlari ----
STATE_CREATED = 1
STATE_PERFORMED = 2
STATE_CANCELLED = -1
STATE_CANCELLED_AFTER = -2

# Payme tranzaksiyani 12 soat ichida yakunlashi kerak
TIMEOUT_MS = 12 * 60 * 60 * 1000


class PaymeError(Exception):
    """JSON-RPC xatolik."""

    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self, request_id=None):
        msg = self.message
        if isinstance(msg, str):
            msg = {"uz": msg, "ru": msg, "en": msg}
        err = {"code": self.code, "message": msg}
        if self.data:
            err["data"] = self.data
        return {"jsonrpc": "2.0", "id": request_id, "error": err}


# ---- Standart xatoliklar ----
ERR_AUTH = (-32504, {
    "uz": "Avtorizatsiyadan o'tilmadi",
    "ru": "Ошибка авторизации",
    "en": "Authorization failed",
})
ERR_PARSE = (-32700, {"uz": "JSON xato", "ru": "Ошибка JSON", "en": "Parse error"})
ERR_REQUEST = (-32600, {"uz": "Noto'g'ri so'rov", "ru": "Неверный запрос", "en": "Invalid request"})
ERR_METHOD = (-32601, {"uz": "Metod topilmadi", "ru": "Метод не найден", "en": "Method not found"})
ERR_AMOUNT = (-31001, {"uz": "Noto'g'ri summa", "ru": "Неверная сумма", "en": "Wrong amount"})
ERR_TX_NOT_FOUND = (-31003, {
    "uz": "Tranzaksiya topilmadi",
    "ru": "Транзакция не найдена",
    "en": "Transaction not found",
})
ERR_CANT_PERFORM = (-31008, {
    "uz": "Amalni bajarib bo'lmadi",
    "ru": "Невозможно выполнить операцию",
    "en": "Unable to perform operation",
})
ERR_CANT_CANCEL = (-31007, {
    "uz": "Buyurtma bajarilgan, bekor qilib bo'lmaydi",
    "ru": "Заказ выполнен, отмена невозможна",
    "en": "Order completed, cannot cancel",
})
ERR_ORDER_NOT_FOUND = (-31050, {
    "uz": "Buyurtma topilmadi",
    "ru": "Заказ не найден",
    "en": "Order not found",
})
ERR_ORDER_PAID = (-31051, {
    "uz": "Buyurtma allaqachon to'langan",
    "ru": "Заказ уже оплачен",
    "en": "Order already paid",
})
ERR_ORDER_CANCELLED = (-31052, {
    "uz": "Buyurtma bekor qilingan",
    "ru": "Заказ отменён",
    "en": "Order cancelled",
})


def _err(pair, data=None):
    return PaymeError(pair[0], pair[1], data)


# =====================================================================
#  1) MERCHANT API  —  Payme -> biz
# =====================================================================
class MerchantAPI:
    """Payme Merchant API JSON-RPC ishlovchisi.

    `account` maydoni sifatida `payment_id` ishlatiladi (kassa sozlamasida
    "payment_id" nomli maydon yaratilishi kerak).
    """

    ACCOUNT_FIELD = "payment_id"

    def __init__(self, on_paid=None, on_cancelled=None):
        self.on_paid = on_paid
        self.on_cancelled = on_cancelled

    # ---------- Avtorizatsiya ----------
    def check_auth(self, auth_header):
        keys = [k for k in (config.PAYME_KEY, config.PAYME_TEST_KEY) if k]
        if not keys:
            # Kalit sozlanmagan — xavfsizlik uchun rad etamiz
            return False
        if not auth_header or not auth_header.lower().startswith("basic "):
            return False
        try:
            raw = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, IndexError):
            return False
        login, _, password = raw.partition(":")
        if login != "Paycom":
            return False
        return password in keys

    # ---------- Kirish nuqtasi ----------
    def handle(self, auth_header, raw_body):
        request_id = None
        try:
            try:
                payload = json.loads(raw_body or "{}")
            except (ValueError, TypeError):
                raise _err(ERR_PARSE)

            if not isinstance(payload, dict):
                raise _err(ERR_REQUEST)

            request_id = payload.get("id")
            method = payload.get("method")
            params = payload.get("params") or {}

            if not self.check_auth(auth_header):
                raise _err(ERR_AUTH)

            handler = {
                "CheckPerformTransaction": self.check_perform_transaction,
                "CreateTransaction": self.create_transaction,
                "PerformTransaction": self.perform_transaction,
                "CancelTransaction": self.cancel_transaction,
                "CheckTransaction": self.check_transaction,
                "GetStatement": self.get_statement,
                "ChangePassword": self.change_password,
            }.get(method)

            if handler is None:
                raise _err(ERR_METHOD, data=str(method))

            result = handler(params)
            return {"jsonrpc": "2.0", "id": request_id, "result": result}

        except PaymeError as exc:
            return exc.to_dict(request_id)
        except Exception as exc:  # kutilmagan xato
            log.exception("Payme merchant xatolik: %s", exc)
            return _err(ERR_CANT_PERFORM).to_dict(request_id)

    # ---------- Yordamchilar ----------
    def _payment_from_account(self, params):
        account = params.get("account") or {}
        raw_id = account.get(self.ACCOUNT_FIELD) or account.get("order_id")
        try:
            payment_id = int(str(raw_id).strip())
        except (TypeError, ValueError):
            raise _err(ERR_ORDER_NOT_FOUND, data=self.ACCOUNT_FIELD)

        row = query("SELECT * FROM payments WHERE id = ?", (payment_id,), one=True)
        if not row:
            raise _err(ERR_ORDER_NOT_FOUND, data=self.ACCOUNT_FIELD)
        return row

    @staticmethod
    def _check_amount(payment, amount_tiyin):
        if int(amount_tiyin or 0) != to_tiyin(payment["amount"]):
            raise _err(ERR_AMOUNT)

    @staticmethod
    def _tx(paycom_id):
        return query(
            "SELECT * FROM payme_transactions WHERE paycom_id = ?", (paycom_id,), one=True
        )

    @staticmethod
    def _tx_dict(tx):
        return {
            "create_time": tx["create_time"],
            "perform_time": tx["perform_time"],
            "cancel_time": tx["cancel_time"],
            "transaction": str(tx["id"]),
            "state": tx["state"],
            "reason": tx["reason"],
        }

    # ---------- Metodlar ----------
    def check_perform_transaction(self, params):
        payment = self._payment_from_account(params)
        self._check_amount(payment, params.get("amount"))

        if payment["status"] == "paid":
            raise _err(ERR_ORDER_PAID, data=self.ACCOUNT_FIELD)
        if payment["status"] == "cancelled":
            raise _err(ERR_ORDER_CANCELLED, data=self.ACCOUNT_FIELD)

        detail = {
            "receipt_type": 0,
            "items": [
                {
                    "title": payment["description"] or "AutoXabar obuna",
                    "price": to_tiyin(payment["amount"]),
                    "count": 1,
                    "code": "10305001001000000",  # IKPU: axborot xizmatlari
                    "vat_percent": 0,
                    "package_code": "1",
                }
            ],
        }
        return {"allow": True, "detail": detail}

    def create_transaction(self, params):
        paycom_id = str(params.get("id") or "")
        if not paycom_id:
            raise _err(ERR_REQUEST)

        existing = self._tx(paycom_id)
        if existing:
            if existing["state"] != STATE_CREATED:
                raise _err(ERR_CANT_PERFORM)
            if self._is_timed_out(existing):
                self._cancel(existing, reason=4)
                raise _err(ERR_CANT_PERFORM)
            return {
                "create_time": existing["create_time"],
                "transaction": str(existing["id"]),
                "state": existing["state"],
            }

        payment = self._payment_from_account(params)
        self._check_amount(payment, params.get("amount"))

        if payment["status"] == "paid":
            raise _err(ERR_ORDER_PAID, data=self.ACCOUNT_FIELD)
        if payment["status"] == "cancelled":
            raise _err(ERR_ORDER_CANCELLED, data=self.ACCOUNT_FIELD)

        # Shu buyurtma uchun boshqa faol tranzaksiya bo'lmasligi kerak
        other = query(
            "SELECT 1 FROM payme_transactions WHERE payment_id = ? AND state = ? LIMIT 1",
            (payment["id"], STATE_CREATED),
            one=True,
        )
        if other:
            raise _err(ERR_CANT_PERFORM)

        create_time = int(params.get("time") or 0)
        tx_id = execute(
            "INSERT INTO payme_transactions(paycom_id, paycom_time, payment_id, "
            "amount_tiyin, state, create_time, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                paycom_id,
                create_time,
                payment["id"],
                to_tiyin(payment["amount"]),
                STATE_CREATED,
                create_time,
                now_str(),
                now_str(),
            ),
        )
        return {
            "create_time": create_time,
            "transaction": str(tx_id),
            "state": STATE_CREATED,
        }

    def perform_transaction(self, params):
        tx = self._tx(str(params.get("id") or ""))
        if not tx:
            raise _err(ERR_TX_NOT_FOUND)

        if tx["state"] == STATE_PERFORMED:
            return {
                "transaction": str(tx["id"]),
                "perform_time": tx["perform_time"],
                "state": tx["state"],
            }
        if tx["state"] != STATE_CREATED:
            raise _err(ERR_CANT_PERFORM)

        if self._is_timed_out(tx):
            self._cancel(tx, reason=4)
            raise _err(ERR_CANT_PERFORM)

        perform_time = _now_ms()
        update(
            "payme_transactions",
            {"state": STATE_PERFORMED, "perform_time": perform_time, "updated_at": now_str()},
            "id = ?",
            (tx["id"],),
        )
        update(
            "payments",
            {
                "status": "paid",
                "paid_at": now_str(),
                "external_id": tx["paycom_id"],
                "updated_at": now_str(),
            },
            "id = ?",
            (tx["payment_id"],),
        )

        if self.on_paid:
            try:
                self.on_paid(tx["payment_id"])
            except Exception:
                log.exception("on_paid callback xatosi (payment %s)", tx["payment_id"])

        return {
            "transaction": str(tx["id"]),
            "perform_time": perform_time,
            "state": STATE_PERFORMED,
        }

    def cancel_transaction(self, params):
        tx = self._tx(str(params.get("id") or ""))
        if not tx:
            raise _err(ERR_TX_NOT_FOUND)

        reason = params.get("reason")

        if tx["state"] in (STATE_CANCELLED, STATE_CANCELLED_AFTER):
            return {
                "transaction": str(tx["id"]),
                "cancel_time": tx["cancel_time"],
                "state": tx["state"],
            }

        if tx["state"] == STATE_PERFORMED:
            # Xizmat ko'rsatilgan bo'lsa ham Payme qaytarishga ruxsat beradi
            new_state = STATE_CANCELLED_AFTER
        else:
            new_state = STATE_CANCELLED

        cancel_time = _now_ms()
        update(
            "payme_transactions",
            {
                "state": new_state,
                "reason": reason,
                "cancel_time": cancel_time,
                "updated_at": now_str(),
            },
            "id = ?",
            (tx["id"],),
        )
        update(
            "payments",
            {"status": "cancelled", "updated_at": now_str()},
            "id = ?",
            (tx["payment_id"],),
        )

        if self.on_cancelled:
            try:
                self.on_cancelled(tx["payment_id"], new_state)
            except Exception:
                log.exception("on_cancelled callback xatosi")

        return {
            "transaction": str(tx["id"]),
            "cancel_time": cancel_time,
            "state": new_state,
        }

    def check_transaction(self, params):
        tx = self._tx(str(params.get("id") or ""))
        if not tx:
            raise _err(ERR_TX_NOT_FOUND)
        return self._tx_dict(tx)

    def get_statement(self, params):
        frm = int(params.get("from") or 0)
        to = int(params.get("to") or 0)
        rows = query(
            "SELECT t.*, p.id AS pid FROM payme_transactions t "
            "JOIN payments p ON p.id = t.payment_id "
            "WHERE t.create_time BETWEEN ? AND ? ORDER BY t.create_time",
            (frm, to),
        )
        out = []
        for tx in rows:
            out.append(
                {
                    "id": tx["paycom_id"],
                    "time": tx["create_time"],
                    "amount": tx["amount_tiyin"],
                    "account": {self.ACCOUNT_FIELD: str(tx["payment_id"])},
                    "create_time": tx["create_time"],
                    "perform_time": tx["perform_time"],
                    "cancel_time": tx["cancel_time"],
                    "transaction": str(tx["id"]),
                    "state": tx["state"],
                    "reason": tx["reason"],
                    "receivers": json.loads(tx["receivers"]) if tx["receivers"] else None,
                }
            )
        return {"transactions": out}

    def change_password(self, params):
        password = params.get("password")
        if not password or password == config.PAYME_KEY:
            raise _err(ERR_CANT_PERFORM)
        # Kalitni .env faylidan almashtirish tavsiya etiladi; bu yerda faqat
        # muvaffaqiyatli javob qaytaramiz, aks holda Payme qayta urinaveradi.
        return {"success": True}

    # ---------- Ichki ----------
    @staticmethod
    def _is_timed_out(tx):
        return (_now_ms() - int(tx["create_time"] or 0)) > TIMEOUT_MS

    @staticmethod
    def _cancel(tx, reason):
        update(
            "payme_transactions",
            {
                "state": STATE_CANCELLED,
                "reason": reason,
                "cancel_time": _now_ms(),
                "updated_at": now_str(),
            },
            "id = ?",
            (tx["id"],),
        )
        update(
            "payments",
            {"status": "cancelled", "updated_at": now_str()},
            "id = ?",
            (tx["payment_id"],),
        )


def _now_ms():
    import time

    return int(time.time() * 1000)


# =====================================================================
#  Checkout havolasi (bir martalik to'lov)
# =====================================================================
def checkout_url(payment_id, amount_soum, callback_url=None, lang="uz"):
    """Payme checkout sahifasiga yo'naltirish havolasi."""
    merchant = config.PAYME_MERCHANT_ID
    if not merchant:
        return ""
    parts = [
        "m={}".format(merchant),
        "ac.{}={}".format(MerchantAPI.ACCOUNT_FIELD, payment_id),
        "a={}".format(to_tiyin(amount_soum)),
        "l={}".format(lang),
        "cr=UZS",
    ]
    if callback_url:
        parts.append("c={}".format(callback_url))
    encoded = base64.b64encode(";".join(parts).encode("utf-8")).decode("ascii")
    return "{}/{}".format(config.PAYME_CHECKOUT_URL, encoded)


# =====================================================================
#  2) SUBSCRIBE API  —  biz -> Payme (karta tokeni, avto-to'lov)
# =====================================================================
class SubscribeAPI:
    """Payme Subscribe API klienti (karta saqlash va avto-to'lov)."""

    def __init__(self, merchant_id=None, key=None, url=None, timeout=25):
        self.merchant_id = merchant_id or config.PAYME_SUBSCRIBE_ID or config.PAYME_MERCHANT_ID
        self.key = key or config.PAYME_SUBSCRIBE_KEY or config.PAYME_KEY
        self.url = (url or config.PAYME_SUBSCRIBE_URL).rstrip("/")
        self.timeout = timeout

    @property
    def configured(self):
        return bool(self.merchant_id and self.key)

    def _call(self, method, params, with_key=False):
        auth = "{}:{}".format(self.merchant_id, self.key) if with_key else self.merchant_id
        headers = {"X-Auth": auth, "Content-Type": "application/json"}
        body = {"id": _now_ms(), "method": method, "params": params}
        try:
            resp = requests.post(
                self.url, json=body, headers=headers, timeout=self.timeout
            )
            data = resp.json()
        except requests.RequestException as exc:
            log.error("Payme Subscribe tarmoq xatosi (%s): %s", method, exc)
            return {"error": {"code": -1, "message": "Tarmoq xatosi: {}".format(exc)}}
        except ValueError:
            log.error("Payme Subscribe JSON xatosi (%s)", method)
            return {"error": {"code": -2, "message": "Javobni o'qib bo'lmadi"}}
        if "error" in data:
            log.warning("Payme Subscribe xatolik (%s): %s", method, data["error"])
        return data

    # ---------- Kartalar ----------
    def cards_create(self, number, expire, save=True):
        """Karta tokenini yaratadi (hali tasdiqlanmagan)."""
        return self._call(
            "cards.create",
            {"card": {"number": number, "expire": expire}, "save": bool(save)},
        )

    def cards_get_verify_code(self, token):
        """Kartaga bog'langan raqamga SMS kod yuboradi."""
        return self._call("cards.get_verify_code", {"token": token})

    def cards_verify(self, token, code):
        """SMS kod bilan tokenni tasdiqlaydi."""
        return self._call("cards.verify", {"token": token, "code": str(code)})

    def cards_check(self, token):
        return self._call("cards.check", {"token": token})

    def cards_remove(self, token):
        return self._call("cards.remove", {"token": token})

    # ---------- Cheklar ----------
    def receipts_create(self, amount_soum, account, description=""):
        return self._call(
            "receipts.create",
            {
                "amount": to_tiyin(amount_soum),
                "account": account,
                "description": description,
                "detail": {
                    "receipt_type": 0,
                    "items": [
                        {
                            "title": description or "AutoXabar obuna",
                            "price": to_tiyin(amount_soum),
                            "count": 1,
                            "code": "10305001001000000",
                            "vat_percent": 0,
                            "package_code": "1",
                        }
                    ],
                },
            },
            with_key=True,
        )

    def receipts_pay(self, receipt_id, token, phone=""):
        params = {"id": receipt_id, "token": token}
        if phone:
            params["payer"] = {"phone": phone}
        return self._call("receipts.pay", params, with_key=True)

    def receipts_check(self, receipt_id):
        return self._call("receipts.check", {"id": receipt_id}, with_key=True)

    def receipts_cancel(self, receipt_id):
        return self._call("receipts.cancel", {"id": receipt_id}, with_key=True)

    # ---------- Yuqori darajali: avto-to'lov ----------
    def charge(self, token, amount_soum, account, description="", phone=""):
        """Saqlangan karta tokenidan pul yechadi.

        Qaytaradi: (ok: bool, receipt_id: str, xato_matni: str)
        """
        created = self.receipts_create(amount_soum, account, description)
        if "error" in created:
            return False, "", _msg(created["error"])

        receipt = (created.get("result") or {}).get("receipt") or {}
        receipt_id = receipt.get("_id", "")
        if not receipt_id:
            return False, "", "Chek yaratilmadi"

        paid = self.receipts_pay(receipt_id, token, phone)
        if "error" in paid:
            return False, receipt_id, _msg(paid["error"])

        state = ((paid.get("result") or {}).get("receipt") or {}).get("state")
        if state == 4:
            return True, receipt_id, ""
        return False, receipt_id, "Chek holati: {}".format(state)


def _msg(error):
    """Payme xatolik xabarini o'qiladigan matnga aylantiradi."""
    if not error:
        return "Noma'lum xatolik"
    message = error.get("message")
    if isinstance(message, dict):
        return message.get("uz") or message.get("ru") or message.get("en") or str(message)
    return str(message or error)


subscribe_api = SubscribeAPI()
