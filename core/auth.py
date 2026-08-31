"""Autentifikatsiya: sessiya, ro'yxatdan o'tish, kirish, ruxsatlar."""
from functools import wraps

from flask import abort, flash, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from core.db import execute, now_str, query
from core.utils import client_ip, gen_ref_code, normalize_phone

SESSION_KEY = "uid"


# ---------------- Foydalanuvchi ----------------
def get_user(user_id):
    return query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)


def get_user_by_phone(phone):
    return query("SELECT * FROM users WHERE phone = ?", (phone,), one=True)


def current_user():
    """Joriy foydalanuvchi (so'rov davomida keshlanadi)."""
    if "user" in g:
        return g.user
    uid = session.get(SESSION_KEY)
    user = get_user(uid) if uid else None
    if user and user["status"] != "active":
        logout()
        user = None
    g.user = user
    return user


def is_admin(user=None):
    user = user or current_user()
    return bool(user and user["role"] == "admin")


# ---------------- Kirish / chiqish ----------------
def login(user, remember=True):
    session.clear()
    session[SESSION_KEY] = user["id"]
    session.permanent = bool(remember)
    g.pop("user", None)
    execute(
        "UPDATE users SET last_login_at = ?, last_ip = ?, updated_at = ? WHERE id = ?",
        (now_str(), client_ip(), now_str(), user["id"]),
    )


def logout():
    session.clear()
    g.pop("user", None)


def verify_password(user, password):
    if not user or not password:
        return False
    return check_password_hash(user["password_hash"], password)


def set_password(user_id, password):
    execute(
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (generate_password_hash(password), now_str(), user_id),
    )


def create_user(phone, password, name="", referrer_id=None, role="user"):
    """Yangi foydalanuvchi yaratadi va id qaytaradi."""
    phone = normalize_phone(phone)
    if not phone:
        raise ValueError("Telefon raqami noto'g'ri")
    if get_user_by_phone(phone):
        raise ValueError("Bu raqam allaqachon ro'yxatdan o'tgan")

    ref_code = gen_ref_code()
    while query("SELECT 1 FROM users WHERE ref_code = ?", (ref_code,), one=True):
        ref_code = gen_ref_code()

    return execute(
        "INSERT INTO users(phone, password_hash, name, role, status, ref_code, "
        "referrer_id, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (
            phone,
            generate_password_hash(password),
            (name or "").strip(),
            role,
            "active",
            ref_code,
            referrer_id,
            now_str(),
            now_str(),
        ),
    )


# ---------------- Dekoratorlar ----------------
def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user():
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return {"ok": False, "error": "auth"}, 401
            flash("Davom etish uchun tizimga kiring", "warning")
            return redirect(url_for("auth.login_view", next=request.full_path))
        return view(*args, **kwargs)

    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for("auth.login_view", next=request.full_path))
        if user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapper


def guest_only(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user():
            return redirect(url_for("cabinet.dashboard"))
        return view(*args, **kwargs)

    return wrapper


# ---------------- Egalik tekshiruvi ----------------
def own_profile_or_404(profile_id):
    user = current_user()
    row = query("SELECT * FROM profiles WHERE id = ?", (profile_id,), one=True)
    if not row:
        abort(404)
    if row["user_id"] != user["id"] and user["role"] != "admin":
        abort(403)
    return row


def own_ad_or_404(ad_id):
    user = current_user()
    row = query("SELECT * FROM ads WHERE id = ?", (ad_id,), one=True)
    if not row:
        abort(404)
    if row["user_id"] != user["id"] and user["role"] != "admin":
        abort(403)
    return row
