"""Payment Hub — kompaniyaning yagona to'lov shlyuzi.

Ilova Click bilan to'g'ridan-to'g'ri ishlamaydi:

    1) POST /v1/payments          — hub'da to'lov yaratamiz, checkout_url olamiz
    2) mijoz checkout_url ga       — Click sahifasi (karta + SMS kod)
    3) hub -> webhook              — payment.succeeded kelganda obuna yoqiladi
    4) GET /v1/payments/{id}       — webhook kelmay qolsa holatni o'zimiz so'raymiz

Muhim qoidalar (hub qo'llanmasidan):
  - summa TIYINDA, butun son (1 so'm = 100 tiyin); bizda payments.amount so'mda
  - har bir POST da Idempotency-Key; tarmoq xatosida o'sha kalit bilan qayta
  - webhook imzosi XOM tana ustidan tekshiriladi, 5 daqiqalik vaqt oynasi bilan
  - holat hodisalar tartibidan emas, payload'dagi `status` dan olinadi
  - payment.expired dan keyin ham payment.succeeded kelishi mumkin
"""
import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from datetime import timedelta

import requests

from config import config
from core.db import execute, get_db, now, now_str, query, update
from core.utils import dt_str

log = logging.getLogger("hub")

TIMEOUT = (5, 15)            # (ulanish, javob) soniya
MAX_ATTEMPTS = 3
SIGNATURE_WINDOW = 300       # 5 daqiqa
POLL_AFTER = timedelta(minutes=2)
POLL_FOR = timedelta(days=2)


class HubError(Exception):
    def __init__(self, code, message="", status=0):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.status = status


def configured():
    return bool(
        config.PAYMENT_HUB_URL
        and config.PAYMENT_HUB_API_KEY
        and config.PAYMENT_HUB_WEBHOOK_SECRET
    )


def webhook_url():
    return config.BASE_URL + "/api/payments/hub/webhook"


# ================================================================== HTTP
def _retry_after(resp, cap=3.0):
    try:
        return min(float(resp.headers.get("Retry-After", 1)), cap)
    except (TypeError, ValueError):
        return 1.0


def _call(method, path, body=None, idempotency_key=None):
    """Hub API ga so'rov. Vaqtinchalik xatolarda o'sha kalit bilan qayta uradi.

    Foydalanuvchi so'rovi ichida chaqirilgani uchun kutish qisqa (jami bir
    necha soniya) — uzoq Retry-After bo'lsa xato qaytariladi.
    """
    headers = {
        "Authorization": "Bearer " + config.PAYMENT_HUB_API_KEY,
        "Accept": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    url = config.PAYMENT_HUB_URL + path

    last = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.request(
                method, url, json=body, headers=headers, timeout=TIMEOUT,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            # Javob kelmadi — hub to'lovni yaratgan bo'lishi mumkin, shuning
            # uchun aynan o'sha Idempotency-Key bilan qayta yuboramiz.
            last = HubError("network_error", str(exc))
            log.warning("Hub %s %s: tarmoq xatosi (%s/%s): %s",
                        method, path, attempt, MAX_ATTEMPTS, exc)
            time.sleep(attempt)
            continue

        try:
            data = resp.json()
        except ValueError:
            data = {}

        if 200 <= resp.status_code < 300:
            return data

        err = data.get("error") if isinstance(data.get("error"), dict) else {}
        last = HubError(
            err.get("code") or "http_{}".format(resp.status_code),
            err.get("message") or resp.text[:200],
            resp.status_code,
        )
        retryable = resp.status_code in (429, 503) or (
            resp.status_code == 409 and last.code == "request_in_progress"
        )
        if not retryable or attempt == MAX_ATTEMPTS:
            break
        time.sleep(_retry_after(resp))

    raise last


# ================================================================== to'lov yaratish
def create_checkout(payment, return_url):
    """Hub'da to'lov yaratadi va mijoz yuboriladigan checkout_url ni qaytaradi.

    `payment` — payments jadvalidagi yozuv (summa so'mda).
    order_id ga tasodifiy qo'shimcha qo'shiladi: baza zaxiradan tiklansa
    payments.id lar takrorlanadi, hub esa order_id ni abadiy eslab qoladi.
    """
    if not configured():
        raise HubError("not_configured", "Payment Hub sozlanmagan")

    order_id = "{}{}-{}".format(
        config.PAYMENT_HUB_ORDER_PREFIX, payment["id"], secrets.token_hex(3)
    )
    idem = str(uuid.uuid4())
    execute(
        "INSERT INTO hub_payments(payment_id, order_id, idempotency_key, provider, "
        "status, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
        (payment["id"], order_id, idem, config.PAYMENT_HUB_PROVIDER, "new",
         now_str(), now_str()),
    )

    metadata = {"payment_id": payment["id"], "user_id": payment["user_id"]}
    if payment["profile_id"]:
        metadata["profile_id"] = payment["profile_id"]

    data = _call(
        "POST",
        "/v1/payments",
        {
            "order_id": order_id,
            "amount": int(payment["amount"]) * 100,   # so'm -> tiyin
            "currency": "UZS",
            "provider": config.PAYMENT_HUB_PROVIDER,
            "return_url": return_url,
            "metadata": metadata,
        },
        idempotency_key=idem,
    )

    update(
        "hub_payments",
        {
            # NULL, "" emas: ustun UNIQUE, bo'sh satrlar o'zaro to'qnashadi
            "hub_payment_id": str(data["payment_id"]) if data.get("payment_id") else None,
            "status": str(data.get("status") or "created"),
            "checkout_url": str(data.get("checkout_url") or ""),
            "expires_at": str(data.get("expires_at") or ""),
            "updated_at": now_str(),
        },
        "order_id = ?",
        (order_id,),
    )
    if not data.get("payment_id") or not data.get("checkout_url"):
        raise HubError("bad_response", "Hub javobida payment_id yoki checkout_url yo'q")
    return data["checkout_url"]


# ================================================================== holatni qo'llash
def _find(hub_payment_id="", order_id=""):
    if hub_payment_id:
        row = query("SELECT * FROM hub_payments WHERE hub_payment_id = ?",
                    (str(hub_payment_id),), one=True)
        if row:
            return row
    if order_id:
        return query("SELECT * FROM hub_payments WHERE order_id = ?",
                     (str(order_id),), one=True)
    return None


def _changed(sql, params):
    """UPDATE bajarib, o'zgargan qatorlar sonini qaytaradi (atomar tekshiruv)."""
    conn = get_db()
    cur = conn.execute(sql, params)
    conn.commit()
    count = cur.rowcount
    cur.close()
    return count


def apply_status(row, data, source=""):
    """Hub'dagi holatni mahalliy to'lovga ko'chiradi (webhook ham, so'rov ham).

    Idempotent: bir xil ma'lumot necha marta kelsa ham obuna bir marta uzayadi.
    """
    from services import billing  # aylanma importdan qochish

    status = str(data.get("status") or "")
    fields = {"status": status or row["status"], "last_event": source, "updated_at": now_str()}
    if data.get("payment_id") and not row["hub_payment_id"]:
        fields["hub_payment_id"] = str(data["payment_id"])
    if data.get("provider_payment_id"):
        fields["provider_payment_id"] = str(data["provider_payment_id"])
    update("hub_payments", fields, "id = ?", (row["id"],))

    payment = query("SELECT * FROM payments WHERE id = ?", (row["payment_id"],), one=True)
    if not payment:
        log.error("Hub: mahalliy to'lov topilmadi (payment %s)", row["payment_id"])
        return

    if status == "succeeded":
        expected = int(payment["amount"]) * 100
        if int(data.get("amount") or 0) != expected:
            log.error(
                "Hub: summa mos emas — kutilgan %s, kelgan %s tiyin (payment %s). "
                "Obuna yoqilmadi, qo'lda tekshiring",
                expected, data.get("amount"), payment["id"],
            )
            return
        # Faqat bitta jarayon/oqim to'lovni "paid" ga o'tkaza oladi —
        # takroriy webhook yoki parallel so'rov obunani ikki marta uzaytirmaydi.
        # expired -> succeeded ham shu yerda: mijoz oxirgi soniyada to'lagan.
        flipped = _changed(
            "UPDATE payments SET status = 'paid', paid_at = ?, external_id = ?, "
            "updated_at = ? WHERE id = ? AND status != 'paid'",
            (now_str(), str(data.get("provider_payment_id") or data.get("payment_id") or ""),
             now_str(), payment["id"]),
        )
        if flipped:
            log.info("Hub: to'lov qabul qilindi (payment %s, %s)", payment["id"], source)
            try:
                billing.on_payment_paid(payment["id"])
            except Exception:
                log.exception(
                    "Hub: to'lov 'paid' bo'ldi, lekin obunani yoqishda xato "
                    "(payment %s) — qo'lda tekshiring", payment["id"],
                )
        return

    if status == "expired":
        if _changed(
            "UPDATE payments SET status = 'cancelled', updated_at = ? "
            "WHERE id = ? AND status = 'pending'",
            (now_str(), payment["id"]),
        ):
            log.info("Hub: to'lov muddati tugadi (payment %s)", payment["id"])
        return

    if status in ("refunded", "partially_refunded") or source in (
        "payment.manual_review", "payment.reversal_pending", "refund.succeeded",
    ):
        log.warning(
            "Hub: %s / %s (payment %s) — obuna va moliya daftari avtomatik "
            "o'zgartirilmaydi, qo'lda tekshiring", source, status, payment["id"],
        )


# ================================================================== webhook
def verify_signature(secret, timestamp, raw_body, signature):
    """X-Hub-Signature = "sha256=" + hex(HMAC-SHA256(sir, timestamp + "." + xom_tana))."""
    if not secret or not timestamp or not str(timestamp).isdigit():
        return False
    if abs(time.time() - int(timestamp)) > SIGNATURE_WINDOW:
        return False
    mac = hmac.new(secret.encode(), str(timestamp).encode() + b"." + raw_body, hashlib.sha256)
    return hmac.compare_digest("sha256=" + mac.hexdigest(), signature or "")


def handle_webhook(headers, raw_body):
    """Webhook'ni qayta ishlaydi. (http_status, json_javob) qaytaradi.

    2xx — hub yetkazildi deb hisoblaydi. Boshqa javobda u qayta yuboradi
    (5 s ... 24 soat), shuning uchun vaqtinchalik xatoda 5xx qaytaramiz.
    """
    if not configured():
        log.error("Hub webhook keldi, lekin PAYMENT_HUB_* sozlanmagan")
        return 503, {"error": "not_configured"}

    if not verify_signature(
        config.PAYMENT_HUB_WEBHOOK_SECRET,
        headers.get("X-Hub-Timestamp", ""),
        raw_body,
        headers.get("X-Hub-Signature", ""),
    ):
        log.warning("Hub webhook: imzo noto'g'ri yoki eskirgan")
        return 401, {"error": "invalid_signature"}

    try:
        data = json.loads(raw_body)
    except ValueError:
        return 400, {"error": "invalid_json"}
    if not isinstance(data, dict):
        return 400, {"error": "invalid_json"}

    delivery = str(headers.get("X-Hub-Delivery", ""))[:100]
    if delivery and query(
        "SELECT 1 FROM hub_webhook_deliveries WHERE delivery_id = ?", (delivery,), one=True
    ):
        return 200, {"ok": True, "duplicate": True}

    event = str(data.get("event") or headers.get("X-Hub-Event", ""))
    row = _find(data.get("payment_id"), data.get("order_id"))
    if not row:
        # Bizning dasturimizning har bir buyurtmasi bizda bo'lishi kerak.
        # 404 — hub qayta urinadi va oxirida administratorni ogohlantiradi.
        log.error("Hub webhook: noma'lum to'lov %s / %s (%s)",
                  data.get("payment_id"), data.get("order_id"), event)
        return 404, {"error": "payment_not_found"}

    apply_status(row, data, event)

    if delivery:
        execute(
            "INSERT OR IGNORE INTO hub_webhook_deliveries(delivery_id, event, "
            "hub_payment_id, received_at) VALUES(?,?,?,?)",
            (delivery, event, str(data.get("payment_id") or ""), now_str()),
        )
    return 200, {"ok": True}


# ================================================================== so'rab tekshirish
def refresh(payment_id):
    """Bitta to'lovning holatini hub'dan so'raydi (natija sahifasi uchun)."""
    row = query("SELECT * FROM hub_payments WHERE payment_id = ?", (payment_id,), one=True)
    if not row or not row["hub_payment_id"] or not configured():
        return
    try:
        data = _call("GET", "/v1/payments/" + row["hub_payment_id"])
    except HubError as exc:
        log.warning("Hub: holatni olib bo'lmadi (payment %s): %s", payment_id, exc.message)
        return
    apply_status(row, data, "poll")


def reconcile_pending():
    """Webhook kelmay qolgan to'lovlarni tekshiradi. Fon jarayoni chaqiradi.

    Ochiq to'lovlar va muddati o'tganlar (keyin succeeded bo'lishi mumkin)
    2 kun davomida kuzatiladi. Qaytaradi: tekshirilganlar soni.
    """
    if not configured():
        return 0
    rows = query(
        "SELECT h.* FROM hub_payments h JOIN payments p ON p.id = h.payment_id "
        "WHERE h.hub_payment_id IS NOT NULL AND h.hub_payment_id != '' "
        "AND (p.status = 'pending' OR (p.status = 'cancelled' AND h.status = 'expired')) "
        "AND h.created_at > ? AND h.updated_at < ? ORDER BY h.id LIMIT 50",
        (dt_str(now() - POLL_FOR), dt_str(now() - POLL_AFTER)),
    )
    for row in rows:
        try:
            data = _call("GET", "/v1/payments/" + row["hub_payment_id"])
        except HubError as exc:
            log.warning("Hub: holatni olib bo'lmadi (payment %s): %s",
                        row["payment_id"], exc.message)
            continue
        apply_status(row, data, "poll")

    # Takroriy webhook'larni aniqlash uchun yozuvlar: hub ~1,5 kun qayta uradi
    execute(
        "DELETE FROM hub_webhook_deliveries WHERE received_at < ?",
        (dt_str(now() - timedelta(days=7)),),
    )
    return len(rows)
