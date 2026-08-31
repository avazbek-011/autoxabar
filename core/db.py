"""SQLite ma'lumotlar bazasi: ulanish, sxema va boshlang'ich ma'lumotlar."""
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from flask import g

from config import config

_local = threading.local()

TZ = timezone(timedelta(hours=5))  # Asia/Tashkent (UTC+5)


def now():
    """Toshkent vaqti bo'yicha hozirgi payt."""
    return datetime.now(TZ)


def now_str():
    return now().strftime("%Y-%m-%d %H:%M:%S")


def today_str():
    return now().strftime("%Y-%m-%d")


def month_str(dt=None):
    return (dt or now()).strftime("%Y-%m")


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ============ FOYDALANUVCHILAR ============
CREATE TABLE IF NOT EXISTS users (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    phone             TEXT    UNIQUE NOT NULL,
    password_hash     TEXT    NOT NULL,
    name              TEXT    NOT NULL DEFAULT '',
    email             TEXT    DEFAULT '',
    telegram_id       TEXT    DEFAULT '',
    telegram_username TEXT    DEFAULT '',
    role              TEXT    NOT NULL DEFAULT 'user',
    status            TEXT    NOT NULL DEFAULT 'active',
    balance           INTEGER NOT NULL DEFAULT 0,
    lang              TEXT    NOT NULL DEFAULT 'uz',
    referrer_id       INTEGER,
    ref_code          TEXT    UNIQUE,
    notes             TEXT    DEFAULT '',
    last_login_at     TEXT,
    last_ip           TEXT    DEFAULT '',
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);

-- ============ TELEGRAM PROFILLARI ============
CREATE TABLE IF NOT EXISTS profiles (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title            TEXT    NOT NULL DEFAULT '',
    phone            TEXT    NOT NULL,
    tg_user_id       TEXT    DEFAULT '',
    tg_username      TEXT    DEFAULT '',
    tg_first_name    TEXT    DEFAULT '',
    session_string   TEXT    DEFAULT '',
    status           TEXT    NOT NULL DEFAULT 'pending',
    status_note      TEXT    DEFAULT '',
    interval_min     INTEGER NOT NULL DEFAULT 10,
    smart_rest       INTEGER NOT NULL DEFAULT 1,
    active_ad_id     INTEGER,
    groups_count     INTEGER NOT NULL DEFAULT 0,
    sent_total       INTEGER NOT NULL DEFAULT 0,
    sent_24h         INTEGER NOT NULL DEFAULT 0,
    failed_total     INTEGER NOT NULL DEFAULT 0,
    last_run_at      TEXT,
    next_run_at      TEXT,
    rest_until       TEXT,
    cycle_started_at TEXT,
    plan             TEXT    NOT NULL DEFAULT 'free',
    expires_at       TEXT,
    auto_renew       INTEGER NOT NULL DEFAULT 1,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_profiles_user ON profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_profiles_status ON profiles(status);

-- ============ XABARLAR (E'LONLAR) ============
CREATE TABLE IF NOT EXISTS ads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT    NOT NULL DEFAULT '',
    body        TEXT    NOT NULL DEFAULT '',
    parse_mode  TEXT    NOT NULL DEFAULT 'html',
    media_path  TEXT    DEFAULT '',
    media_type  TEXT    DEFAULT '',
    buttons     TEXT    DEFAULT '',
    is_active   INTEGER NOT NULL DEFAULT 1,
    sent_count  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ads_user ON ads(user_id);

-- ============ GURUHLAR ============
CREATE TABLE IF NOT EXISTS groups (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id    INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    chat_id       TEXT    NOT NULL,
    title         TEXT    NOT NULL DEFAULT '',
    username      TEXT    DEFAULT '',
    members       INTEGER NOT NULL DEFAULT 0,
    enabled       INTEGER NOT NULL DEFAULT 1,
    status        TEXT    NOT NULL DEFAULT 'ok',
    status_note   TEXT    DEFAULT '',
    slowmode_sec  INTEGER NOT NULL DEFAULT 0,
    sent_count    INTEGER NOT NULL DEFAULT 0,
    fail_count    INTEGER NOT NULL DEFAULT 0,
    last_sent_at  TEXT,
    created_at    TEXT    NOT NULL,
    UNIQUE(profile_id, chat_id)
);
CREATE INDEX IF NOT EXISTS idx_groups_profile ON groups(profile_id);

-- ============ YUBORISH JURNALI ============
CREATE TABLE IF NOT EXISTS send_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id  INTEGER NOT NULL,
    group_id    INTEGER,
    ad_id       INTEGER,
    chat_title  TEXT    DEFAULT '',
    status      TEXT    NOT NULL,
    error       TEXT    DEFAULT '',
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sendlog_profile ON send_log(profile_id, created_at);
CREATE INDEX IF NOT EXISTS idx_sendlog_date ON send_log(created_at);

-- ============ KUNLIK STATISTIKA ============
CREATE TABLE IF NOT EXISTS stats_daily (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    day         TEXT    NOT NULL,
    user_id     INTEGER NOT NULL DEFAULT 0,
    profile_id  INTEGER NOT NULL DEFAULT 0,
    sent        INTEGER NOT NULL DEFAULT 0,
    failed      INTEGER NOT NULL DEFAULT 0,
    UNIQUE(day, user_id, profile_id)
);

-- ============ OBUNALAR ============
CREATE TABLE IF NOT EXISTS subscriptions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_id     INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    plan           TEXT    NOT NULL DEFAULT 'pro',
    price          INTEGER NOT NULL,
    period_days    INTEGER NOT NULL DEFAULT 30,
    status         TEXT    NOT NULL DEFAULT 'active',
    auto_renew     INTEGER NOT NULL DEFAULT 1,
    card_id        INTEGER,
    started_at     TEXT    NOT NULL,
    expires_at     TEXT    NOT NULL,
    renewed_count  INTEGER NOT NULL DEFAULT 0,
    last_charge_at TEXT,
    next_charge_at TEXT,
    fail_count     INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_subs_profile ON subscriptions(profile_id);
CREATE INDEX IF NOT EXISTS idx_subs_next ON subscriptions(status, auto_renew, next_charge_at);

-- ============ SAQLANGAN KARTALAR (Payme token) ============
CREATE TABLE IF NOT EXISTS cards (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token         TEXT    NOT NULL,
    number_masked TEXT    NOT NULL DEFAULT '',
    expire        TEXT    DEFAULT '',
    card_type     TEXT    DEFAULT 'uzcard',
    verified      INTEGER NOT NULL DEFAULT 0,
    is_default    INTEGER NOT NULL DEFAULT 0,
    recurrent     INTEGER NOT NULL DEFAULT 1,
    status        TEXT    NOT NULL DEFAULT 'active',
    created_at    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cards_user ON cards(user_id);

-- ============ TO'LOVLAR ============
CREATE TABLE IF NOT EXISTS payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_id      INTEGER,
    subscription_id INTEGER,
    amount          INTEGER NOT NULL,
    method          TEXT    NOT NULL DEFAULT 'payme',
    kind            TEXT    NOT NULL DEFAULT 'subscription',
    status          TEXT    NOT NULL DEFAULT 'pending',
    description     TEXT    DEFAULT '',
    external_id     TEXT    DEFAULT '',
    paid_at         TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status, created_at);

-- ============ PAYME TRANZAKSIYALARI ============
CREATE TABLE IF NOT EXISTS payme_transactions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    paycom_id    TEXT    UNIQUE NOT NULL,
    paycom_time  INTEGER NOT NULL DEFAULT 0,
    payment_id   INTEGER NOT NULL,
    amount_tiyin INTEGER NOT NULL,
    state        INTEGER NOT NULL DEFAULT 1,
    reason       INTEGER,
    create_time  INTEGER NOT NULL DEFAULT 0,
    perform_time INTEGER NOT NULL DEFAULT 0,
    cancel_time  INTEGER NOT NULL DEFAULT 0,
    receivers    TEXT    DEFAULT '',
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ptx_payment ON payme_transactions(payment_id);

-- ============ MOLIYA DAFTARI ============
CREATE TABLE IF NOT EXISTS finance_ledger (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    day           TEXT    NOT NULL,
    month         TEXT    NOT NULL,
    payment_id    INTEGER,
    user_id       INTEGER,
    gross         INTEGER NOT NULL DEFAULT 0,
    acquiring_fee INTEGER NOT NULL DEFAULT 0,
    tax           INTEGER NOT NULL DEFAULT 0,
    net           INTEGER NOT NULL DEFAULT 0,
    tax_percent   REAL    NOT NULL DEFAULT 0,
    fee_percent   REAL    NOT NULL DEFAULT 0,
    note          TEXT    DEFAULT '',
    created_at    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_month ON finance_ledger(month);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ledger_payment ON finance_ledger(payment_id);

-- ============ CHIQIMLAR ============
CREATE TABLE IF NOT EXISTS expenses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    day        TEXT    NOT NULL,
    month      TEXT    NOT NULL,
    category   TEXT    NOT NULL DEFAULT 'other',
    title      TEXT    NOT NULL DEFAULT '',
    amount     INTEGER NOT NULL DEFAULT 0,
    note       TEXT    DEFAULT '',
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_expenses_month ON expenses(month);

-- ============ YECHIB OLISHLAR (bank) ============
CREATE TABLE IF NOT EXISTS payouts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    month       TEXT    NOT NULL,
    amount      INTEGER NOT NULL,
    kind        TEXT    NOT NULL DEFAULT 'net',
    destination TEXT    DEFAULT '',
    note        TEXT    DEFAULT '',
    paid_at     TEXT    NOT NULL,
    created_by  INTEGER,
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_payouts_month ON payouts(month);

-- ============ SOZLAMALAR ============
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

-- ============ BILDIRISHNOMALAR ============
CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    title      TEXT    NOT NULL DEFAULT '',
    body       TEXT    NOT NULL DEFAULT '',
    kind       TEXT    NOT NULL DEFAULT 'info',
    is_read    INTEGER NOT NULL DEFAULT 0,
    link       TEXT    DEFAULT '',
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, is_read);

-- ============ AUDIT ============
CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER,
    action     TEXT    NOT NULL,
    target     TEXT    DEFAULT '',
    meta       TEXT    DEFAULT '',
    ip         TEXT    DEFAULT '',
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);

-- ============ LOGIN URINISHLARI ============
CREATE TABLE IF NOT EXISTS login_attempts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ident      TEXT    NOT NULL,
    ip         TEXT    DEFAULT '',
    ok         INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts ON login_attempts(ident, created_at);
"""


def connect():
    """Yangi ulanish (har bir thread uchun alohida)."""
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _in_app_context():
    try:
        return bool(g)
    except RuntimeError:
        return False


def get_db():
    """Flask so'rovi doirasidagi (yoki thread-local) ulanish."""
    if _in_app_context():
        if "db" not in g:
            g.db = connect()
        return g.db
    if getattr(_local, "db", None) is None:
        _local.db = connect()
    return _local.db


def close_db(exc=None):
    if _in_app_context():
        db = g.pop("db", None)
        if db is not None:
            db.close()


@contextmanager
def worker_db():
    """Fon jarayonlari uchun mustaqil ulanish."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------- Qulay yordamchilar ----------
def query(sql, params=(), one=False, db=None):
    cur = (db or get_db()).execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, params=(), db=None, commit=True):
    conn = db or get_db()
    cur = conn.execute(sql, params)
    if commit:
        conn.commit()
    lastid = cur.lastrowid
    cur.close()
    return lastid


def scalar(sql, params=(), default=0, db=None):
    row = query(sql, params, one=True, db=db)
    if not row or row[0] is None:
        return default
    return row[0]


def insert(table, data, db=None):
    keys = list(data.keys())
    sql = "INSERT INTO {} ({}) VALUES ({})".format(
        table, ", ".join(keys), ", ".join("?" for _ in keys)
    )
    return execute(sql, tuple(data[k] for k in keys), db=db)


def update(table, data, where, params=(), db=None):
    keys = list(data.keys())
    sql = "UPDATE {} SET {} WHERE {}".format(
        table, ", ".join("{} = ?".format(k) for k in keys), where
    )
    return execute(sql, tuple(data[k] for k in keys) + tuple(params), db=db)


# ---------- Sozlamalar ----------
def get_setting(key, default=None, db=None):
    row = query("SELECT value FROM settings WHERE key = ?", (key,), one=True, db=db)
    return row["value"] if row else default


def set_setting(key, value, db=None):
    execute(
        "INSERT INTO settings(key, value, updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
        "updated_at = excluded.updated_at",
        (key, str(value), now_str()),
        db=db,
    )


def get_setting_float(key, default=0.0, db=None):
    try:
        return float(get_setting(key, default, db=db))
    except (TypeError, ValueError):
        return float(default)


def get_setting_int(key, default=0, db=None):
    try:
        return int(float(get_setting(key, default, db=db)))
    except (TypeError, ValueError):
        return int(default)


DEFAULT_SETTINGS = {
    "telegram_engine": "auto",
    "support_channel": "",
    "support_bot": "",
    "support_contact": "",

    "site_open": "1",
    "registration_open": "1",
    "maintenance_note": "",
    "free_plan_enabled": "1",
    "max_profiles_per_user": "0",   # 0 = cheksiz
    "announce": "",
    "bank_name": "",
    "bank_account": "",
}


def init_db():
    """Sxemani yaratish, boshlang'ich sozlamalar va birinchi admin."""
    import secrets

    from werkzeug.security import generate_password_hash

    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()

        defaults = dict(DEFAULT_SETTINGS)
        defaults["price_per_profile"] = str(config.PRICE_PER_PROFILE)
        defaults["tax_percent"] = str(config.TAX_PERCENT)
        defaults["acquiring_percent"] = str(config.ACQUIRING_PERCENT)
        defaults["trial_days"] = str(config.TRIAL_DAYS)

        for key, val in defaults.items():
            exists = conn.execute(
                "SELECT 1 FROM settings WHERE key = ?", (key,)
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO settings(key, value, updated_at) VALUES(?,?,?)",
                    (key, str(val), now_str()),
                )
        conn.commit()

        has_admin = conn.execute(
            "SELECT 1 FROM users WHERE role = 'admin' LIMIT 1"
        ).fetchone()
        if not has_admin:
            conn.execute(
                "INSERT INTO users(phone, password_hash, name, role, status, ref_code, "
                "created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    config.ADMIN_PHONE,
                    generate_password_hash(config.ADMIN_PASSWORD),
                    config.ADMIN_NAME,
                    "admin",
                    "active",
                    secrets.token_hex(4).upper(),
                    now_str(),
                    now_str(),
                ),
            )
            conn.commit()
    finally:
        conn.close()
