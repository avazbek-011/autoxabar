"""Umumiy yordamchi funksiyalar: formatlash, validatsiya, xavfsizlik."""
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta

from flask import request, session

from core.db import TZ, now, now_str, query, execute

PHONE_RE = re.compile(r"^\+998\d{9}$")


# ---------------- Telefon ----------------
def normalize_phone(raw):
    """+998901234567 ko'rinishiga keltiradi. Noto'g'ri bo'lsa None."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if digits.startswith("998") and len(digits) == 12:
        pass
    elif len(digits) == 9:
        digits = "998" + digits
    elif digits.startswith("8") and len(digits) == 10:
        digits = "998" + digits[1:]
    else:
        return None
    phone = "+" + digits
    return phone if PHONE_RE.match(phone) else None


def pretty_phone(phone):
    """+998901234567 -> +998 90 123 45 67"""
    if not phone or len(phone) != 13:
        return phone or ""
    return "{} {} {} {} {}".format(
        phone[:4], phone[4:6], phone[6:9], phone[9:11], phone[11:13]
    )


# ---------------- Formatlash ----------------
def money(value, suffix=" so'm"):
    """12345 -> '12 345 so'm'"""
    try:
        value = int(round(float(value or 0)))
    except (TypeError, ValueError):
        value = 0
    sign = "-" if value < 0 else ""
    text = "{:,}".format(abs(value)).replace(",", " ")
    return "{}{}{}".format(sign, text, suffix)


def num(value):
    try:
        value = int(value or 0)
    except (TypeError, ValueError):
        value = 0
    return "{:,}".format(value).replace(",", " ")


def compact(value):
    """4500000 -> 4.5M"""
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    for limit, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if abs(value) >= limit:
            out = value / limit
            return ("{:.1f}".format(out).rstrip("0").rstrip(".")) + suffix
    return str(int(value))


def parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=TZ)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value)[:19], fmt).replace(tzinfo=TZ)
        except ValueError:
            continue
    return None


def dt_fmt(value, fmt="%d.%m.%Y %H:%M"):
    dt = parse_dt(value)
    return dt.strftime(fmt) if dt else "—"


def date_fmt(value):
    return dt_fmt(value, "%d.%m.%Y")


def time_left(value):
    """Muddat tugashigacha qolgan vaqt (matn)."""
    dt = parse_dt(value)
    if not dt:
        return "—"
    delta = dt - now()
    total = int(delta.total_seconds())
    if total <= 0:
        return "tugagan"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return "{} kun {} soat".format(days, hours)
    if hours:
        return "{} soat {} daq".format(hours, minutes)
    return "{} daqiqa".format(max(minutes, 1))


def time_ago(value):
    dt = parse_dt(value)
    if not dt:
        return "—"
    total = int((now() - dt).total_seconds())
    if total < 60:
        return "hozirgina"
    if total < 3600:
        return "{} daqiqa oldin".format(total // 60)
    if total < 86400:
        return "{} soat oldin".format(total // 3600)
    if total < 2592000:
        return "{} kun oldin".format(total // 86400)
    return dt.strftime("%d.%m.%Y")


def human_seconds(total):
    """84713 -> "23 soat 32 daqiqa" """
    try:
        total = int(total)
    except (TypeError, ValueError):
        return "biroz"
    if total <= 0:
        return "0 soniya"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days:
        return "{} kun {} soat".format(days, hours)
    if hours:
        return "{} soat {} daqiqa".format(hours, minutes)
    if minutes:
        return "{} daqiqa".format(minutes)
    return "{} soniya".format(seconds)


def plus_days(days, from_dt=None):
    return (from_dt or now()) + timedelta(days=int(days))


def dt_str(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


# ---------------- Xavfsizlik ----------------
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def csrf_valid(token=None):
    token = token or request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
    stored = session.get("_csrf", "")
    return bool(stored) and hmac.compare_digest(str(stored), str(token))


def client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or ""


def gen_code(length=6):
    return "".join(secrets.choice("0123456789") for _ in range(length))


def gen_ref_code():
    return secrets.token_hex(4).upper()


# ---------------- Rate limit ----------------
def rate_limited(ident, limit=6, window_min=15):
    """Oxirgi `window_min` daqiqada muvaffaqiyatsiz urinishlar sonini tekshiradi."""
    since = (now() - timedelta(minutes=window_min)).strftime("%Y-%m-%d %H:%M:%S")
    row = query(
        "SELECT COUNT(*) AS c FROM login_attempts "
        "WHERE ident = ? AND ok = 0 AND created_at > ?",
        (ident, since),
        one=True,
    )
    return (row["c"] if row else 0) >= limit


def log_attempt(ident, ok):
    execute(
        "INSERT INTO login_attempts(ident, ip, ok, created_at) VALUES(?,?,?,?)",
        (ident, client_ip(), 1 if ok else 0, now_str()),
    )


# ---------------- Audit ----------------
def audit(user_id, action, target="", meta=None):
    execute(
        "INSERT INTO audit_log(user_id, action, target, meta, ip, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (
            user_id,
            action,
            str(target),
            json.dumps(meta, ensure_ascii=False) if meta else "",
            client_ip(),
            now_str(),
        ),
    )


# ---------------- Bildirishnoma ----------------
def notify(user_id, title, body="", kind="info", link=""):
    execute(
        "INSERT INTO notifications(user_id, title, body, kind, link, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (user_id, title, body, kind, link, now_str()),
    )


# ---------------- Matn ----------------
TAG_RE = re.compile(r"<[^>]+>")
ALLOWED_TAGS = ("b", "strong", "i", "em", "u", "s", "code", "pre", "a", "br")


def strip_tags(text):
    return TAG_RE.sub("", text or "")


def sanitize_ad_html(text):
    """Telegram qo'llab-quvvatlaydigan teglarni qoldiradi, qolganini olib tashlaydi."""
    if not text:
        return ""

    def repl(match):
        tag = match.group(0)
        name = re.sub(r"[^a-zA-Z]", "", tag.split(" ")[0])
        if name.lower() in ALLOWED_TAGS:
            return tag
        return ""

    return TAG_RE.sub(repl, text)


def truncate(text, length=90):
    text = strip_tags(text or "").strip()
    return text if len(text) <= length else text[: length - 1] + "…"


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def safe_int(value, default=0, minimum=None, maximum=None):
    try:
        out = int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return default
    if minimum is not None and out < minimum:
        return minimum
    if maximum is not None and out > maximum:
        return maximum
    return out
