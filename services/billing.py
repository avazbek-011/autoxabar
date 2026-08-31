"""Obuna va to'lovlar mantiqi.

Narx: 1 profil = 1 oy = `price_per_profile` (sukut bo'yicha 5 000 so'm).
Avto-to'lov Payme Subscribe API orqali saqlangan karta tokenidan yechiladi.
"""
import logging
from datetime import timedelta

from core.db import (
    execute,
    get_setting_int,
    now,
    now_str,
    query,
    update,
)
from core.utils import dt_str, notify, parse_dt, plus_days
from services import finance
from services.payme import subscribe_api

log = logging.getLogger("billing")

PERIOD_DAYS = 30
MAX_CHARGE_FAILS = 3


def price(db=None):
    return get_setting_int("price_per_profile", 5000, db=db)


def trial_days(db=None):
    return get_setting_int("trial_days", 3, db=db)


# ------------------------------------------------------------------ to'lov
def create_payment(
    user_id,
    amount,
    profile_id=None,
    subscription_id=None,
    kind="subscription",
    method="payme",
    description="",
    db=None,
):
    return execute(
        "INSERT INTO payments(user_id, profile_id, subscription_id, amount, method, "
        "kind, status, description, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            user_id,
            profile_id,
            subscription_id,
            int(amount),
            method,
            kind,
            "pending",
            description,
            now_str(),
            now_str(),
        ),
        db=db,
    )


def mark_paid(payment_id, external_id="", db=None):
    update(
        "payments",
        {
            "status": "paid",
            "paid_at": now_str(),
            "external_id": external_id,
            "updated_at": now_str(),
        },
        "id = ?",
        (payment_id,),
        db=db,
    )
    return on_payment_paid(payment_id, db=db)


def on_payment_paid(payment_id, db=None):
    """To'lov muvaffaqiyatli bo'lganda chaqiriladi.

    - moliya daftariga yozadi
    - obunani faollashtiradi / uzaytiradi
    """
    payment = query("SELECT * FROM payments WHERE id = ?", (payment_id,), one=True, db=db)
    if not payment or payment["status"] != "paid":
        return False

    finance.record_revenue(payment_id, db=db)

    if payment["kind"] == "topup":
        execute(
            "UPDATE users SET balance = balance + ?, updated_at = ? WHERE id = ?",
            (payment["amount"], now_str(), payment["user_id"]),
            db=db,
        )
        notify(
            payment["user_id"],
            "Balans to'ldirildi",
            "Hisobingizga {} so'm qo'shildi.".format(payment["amount"]),
            "success",
        )
        return True

    if payment["profile_id"]:
        extend_subscription(
            payment["user_id"],
            payment["profile_id"],
            days=PERIOD_DAYS,
            amount=payment["amount"],
            db=db,
        )
    return True


# ------------------------------------------------------------------ obuna
def get_subscription(profile_id, db=None):
    return query(
        "SELECT * FROM subscriptions WHERE profile_id = ? ORDER BY id DESC LIMIT 1",
        (profile_id,),
        one=True,
        db=db,
    )


def start_trial(user_id, profile_id, db=None):
    """Yangi profil uchun bepul sinov muddati."""
    days = trial_days(db=db)
    if days <= 0:
        return None
    expires = plus_days(days)
    sub_id = execute(
        "INSERT INTO subscriptions(user_id, profile_id, plan, price, period_days, "
        "status, auto_renew, started_at, expires_at, next_charge_at, created_at, "
        "updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            user_id,
            profile_id,
            "trial",
            0,
            days,
            "trial",
            1,
            now_str(),
            dt_str(expires),
            dt_str(expires),
            now_str(),
            now_str(),
        ),
        db=db,
    )
    update(
        "profiles",
        {"plan": "pro", "expires_at": dt_str(expires), "updated_at": now_str()},
        "id = ?",
        (profile_id,),
        db=db,
    )
    return sub_id


def extend_subscription(user_id, profile_id, days=PERIOD_DAYS, amount=None, db=None):
    """Obunani uzaytiradi (mavjud muddat tugamagan bo'lsa — ustiga qo'shadi)."""
    amount = price(db=db) if amount is None else int(amount)
    sub = get_subscription(profile_id, db=db)
    profile = query("SELECT * FROM profiles WHERE id = ?", (profile_id,), one=True, db=db)
    if not profile:
        return None

    current_end = parse_dt(profile["expires_at"])
    base = current_end if current_end and current_end > now() else now()
    new_end = base + timedelta(days=int(days))

    if sub and sub["status"] in ("active", "trial"):
        update(
            "subscriptions",
            {
                "plan": "pro",
                "price": amount,
                "period_days": days,
                "status": "active",
                "expires_at": dt_str(new_end),
                "next_charge_at": dt_str(new_end),
                "last_charge_at": now_str(),
                "renewed_count": sub["renewed_count"] + 1,
                "fail_count": 0,
                "updated_at": now_str(),
            },
            "id = ?",
            (sub["id"],),
            db=db,
        )
        sub_id = sub["id"]
    else:
        sub_id = execute(
            "INSERT INTO subscriptions(user_id, profile_id, plan, price, period_days, "
            "status, auto_renew, started_at, expires_at, next_charge_at, "
            "last_charge_at, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                user_id,
                profile_id,
                "pro",
                amount,
                days,
                "active",
                1,
                now_str(),
                dt_str(new_end),
                dt_str(new_end),
                now_str(),
                now_str(),
                now_str(),
            ),
            db=db,
        )

    update(
        "profiles",
        {"plan": "pro", "expires_at": dt_str(new_end), "updated_at": now_str()},
        "id = ?",
        (profile_id,),
        db=db,
    )
    # To'xtatilgan profilni qayta ishga tushiramiz
    if profile["status"] == "expired":
        update(
            "profiles",
            {"status": "paused", "status_note": "", "updated_at": now_str()},
            "id = ?",
            (profile_id,),
            db=db,
        )

    notify(
        user_id,
        "Obuna faollashtirildi",
        "«{}» profili {} gacha PRO rejimda ishlaydi.".format(
            profile["title"] or profile["phone"], new_end.strftime("%d.%m.%Y")
        ),
        "success",
        "/kabinet/profillar",
    )
    return sub_id


def cancel_auto_renew(profile_id, on=False, db=None):
    update(
        "subscriptions",
        {"auto_renew": 1 if on else 0, "updated_at": now_str()},
        "profile_id = ?",
        (profile_id,),
        db=db,
    )
    update(
        "profiles",
        {"auto_renew": 1 if on else 0, "updated_at": now_str()},
        "id = ?",
        (profile_id,),
        db=db,
    )


def pay_from_balance(user_id, profile_id, db=None):
    """Ichki balansdan to'lash. (ok, xabar)"""
    amount = price(db=db)
    user = query("SELECT * FROM users WHERE id = ?", (user_id,), one=True, db=db)
    if not user or user["balance"] < amount:
        return False, "Balansda mablag' yetarli emas"

    execute(
        "UPDATE users SET balance = balance - ?, updated_at = ? WHERE id = ?",
        (amount, now_str(), user_id),
        db=db,
    )
    payment_id = create_payment(
        user_id,
        amount,
        profile_id=profile_id,
        method="balance",
        description="Obuna (balansdan)",
        db=db,
    )
    update(
        "payments",
        {"status": "paid", "paid_at": now_str(), "updated_at": now_str()},
        "id = ?",
        (payment_id,),
        db=db,
    )
    # Balansdan to'langanda tushum allaqachon hisobga olingan (balans to'ldirilganda)
    extend_subscription(user_id, profile_id, amount=amount, db=db)
    return True, "Obuna faollashtirildi"


# ------------------------------------------------- avto-to'lov (Payme token)
def default_card(user_id, db=None):
    return query(
        "SELECT * FROM cards WHERE user_id = ? AND status = 'active' AND verified = 1 "
        "ORDER BY is_default DESC, id DESC LIMIT 1",
        (user_id,),
        one=True,
        db=db,
    )


def charge_subscription(sub, db=None):
    """Bitta obuna uchun avto-to'lovni amalga oshiradi. (ok, xabar)"""
    card = None
    if sub["card_id"]:
        card = query(
            "SELECT * FROM cards WHERE id = ? AND status = 'active' AND verified = 1",
            (sub["card_id"],),
            one=True,
            db=db,
        )
    if not card:
        card = default_card(sub["user_id"], db=db)
    if not card:
        return False, "Saqlangan karta topilmadi"

    if not subscribe_api.configured:
        return False, "Payme Subscribe sozlanmagan"

    amount = sub["price"] or price(db=db)
    profile = query(
        "SELECT * FROM profiles WHERE id = ?", (sub["profile_id"],), one=True, db=db
    )
    user = query("SELECT * FROM users WHERE id = ?", (sub["user_id"],), one=True, db=db)

    payment_id = create_payment(
        sub["user_id"],
        amount,
        profile_id=sub["profile_id"],
        subscription_id=sub["id"],
        method="payme_auto",
        description="Avto-to'lov: {}".format(
            (profile["title"] if profile else "") or (profile["phone"] if profile else "")
        ),
        db=db,
    )

    ok, receipt_id, error = subscribe_api.charge(
        card["token"],
        amount,
        {"payment_id": str(payment_id)},
        description="AutoXabar obuna (30 kun)",
        phone=(user["phone"] if user else ""),
    )

    if ok:
        update(
            "payments",
            {
                "status": "paid",
                "paid_at": now_str(),
                "external_id": receipt_id,
                "updated_at": now_str(),
            },
            "id = ?",
            (payment_id,),
            db=db,
        )
        on_payment_paid(payment_id, db=db)
        update(
            "subscriptions",
            {"card_id": card["id"], "fail_count": 0, "updated_at": now_str()},
            "id = ?",
            (sub["id"],),
            db=db,
        )
        return True, "To'lov muvaffaqiyatli"

    update(
        "payments",
        {"status": "failed", "external_id": receipt_id, "updated_at": now_str()},
        "id = ?",
        (payment_id,),
        db=db,
    )
    fails = sub["fail_count"] + 1
    # Keyingi urinish 6 soatdan keyin
    update(
        "subscriptions",
        {
            "fail_count": fails,
            "next_charge_at": dt_str(now() + timedelta(hours=6)),
            "updated_at": now_str(),
        },
        "id = ?",
        (sub["id"],),
        db=db,
    )

    if fails == 1:
        notify(
            sub["user_id"],
            "Avto-to'lov amalga oshmadi",
            "Kartadan {} so'm yechib bo'lmadi: {}. Kartada mablag' borligini "
            "tekshiring — 6 soatdan so'ng qayta urinamiz.".format(amount, error),
            "warning",
            "/kabinet/tolovlar",
        )
    elif fails >= MAX_CHARGE_FAILS:
        update(
            "subscriptions",
            {"auto_renew": 0, "updated_at": now_str()},
            "id = ?",
            (sub["id"],),
            db=db,
        )
        notify(
            sub["user_id"],
            "Avto-to'lov o'chirildi",
            "{} marta urinish muvaffaqiyatsiz tugadi. Obunani qo'lda "
            "yangilashingiz mumkin.".format(fails),
            "danger",
            "/kabinet/tolovlar",
        )
    return False, error


def charge_due_subscriptions(db=None):
    """Muddati kelgan barcha avto-obunalarni to'laydi. Fon jarayoni chaqiradi."""
    rows = query(
        "SELECT * FROM subscriptions WHERE status IN ('active','trial') "
        "AND auto_renew = 1 AND next_charge_at IS NOT NULL AND next_charge_at <= ? "
        "AND fail_count < ?",
        (now_str(), MAX_CHARGE_FAILS),
        db=db,
    )
    done, failed = 0, 0
    for sub in rows:
        try:
            ok, _ = charge_subscription(sub, db=db)
            done += 1 if ok else 0
            failed += 0 if ok else 1
        except Exception:
            log.exception("Avto-to'lov xatosi (subscription %s)", sub["id"])
            failed += 1
    return done, failed


def expire_overdue(db=None):
    """Muddati tugagan obunalarni yopadi va profillarni to'xtatadi."""
    rows = query(
        "SELECT * FROM subscriptions WHERE status IN ('active','trial') AND expires_at <= ?",
        (now_str(),),
        db=db,
    )
    count = 0
    for sub in rows:
        # Avto-to'lov hali urinayotgan bo'lsa, biroz kutamiz
        if sub["auto_renew"] and sub["fail_count"] < MAX_CHARGE_FAILS:
            grace = parse_dt(sub["expires_at"])
            if grace and (now() - grace) < timedelta(hours=12):
                continue

        update(
            "subscriptions",
            {"status": "expired", "updated_at": now_str()},
            "id = ?",
            (sub["id"],),
            db=db,
        )
        update(
            "profiles",
            {
                "plan": "free",
                "status": "expired",
                "status_note": "Obuna muddati tugadi",
                "updated_at": now_str(),
            },
            "id = ? AND status != 'banned'",
            (sub["profile_id"],),
            db=db,
        )
        notify(
            sub["user_id"],
            "Obuna muddati tugadi",
            "Profil to'xtatildi. Qayta ishga tushirish uchun obunani yangilang.",
            "warning",
            "/kabinet/tolovlar",
        )
        count += 1
    return count


def notify_expiring(db=None):
    """Muddati 3 kun ichida tugaydiganlarni ogohlantiradi."""
    soon = dt_str(now() + timedelta(days=3))
    rows = query(
        "SELECT s.*, p.title, p.phone FROM subscriptions s "
        "JOIN profiles p ON p.id = s.profile_id "
        "WHERE s.status IN ('active','trial') AND s.auto_renew = 0 "
        "AND s.expires_at BETWEEN ? AND ?",
        (now_str(), soon),
        db=db,
    )
    for sub in rows:
        exists = query(
            "SELECT 1 FROM notifications WHERE user_id = ? AND title = ? "
            "AND created_at > ? LIMIT 1",
            (sub["user_id"], "Obuna tugayapti", dt_str(now() - timedelta(days=2))),
            one=True,
            db=db,
        )
        if exists:
            continue
        notify(
            sub["user_id"],
            "Obuna tugayapti",
            "«{}» profilining obunasi tez orada tugaydi. Uzluksiz ishlashi uchun "
            "avto-to'lovni yoqing.".format(sub["title"] or sub["phone"]),
            "warning",
            "/kabinet/tolovlar",
        )
    return len(rows)
