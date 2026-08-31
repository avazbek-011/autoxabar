"""Ro'yxatdan o'tish, kirish, chiqish, parolni tiklash."""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from core.auth import (
    create_user,
    current_user,
    get_user_by_phone,
    guest_only,
    login,
    login_required,
    logout,
    set_password,
    verify_password,
)
from core.db import get_setting, query
from core.utils import audit, gen_code, log_attempt, normalize_phone, rate_limited

bp = Blueprint("auth", __name__)


def _safe_next(target):
    """Faqat ichki manzillarga yo'naltiramiz."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target.split("?")[0] if target.endswith("?") else target
    return None


# ------------------------------------------------------------------ kirish
@bp.route("/kirish", methods=["GET", "POST"])
@guest_only
def login_view():
    if request.method == "POST":
        phone = normalize_phone(request.form.get("phone"))
        password = request.form.get("password") or ""
        remember = bool(request.form.get("remember"))

        if not phone:
            flash("Telefon raqamini to‘g‘ri kiriting", "error")
            return render_template("auth/login.html", phone=request.form.get("phone"))

        if rate_limited(phone, limit=6, window_min=15):
            flash("Juda ko‘p urinish. 15 daqiqadan so‘ng qayta urinib ko‘ring", "error")
            return render_template("auth/login.html", phone=phone)

        user = get_user_by_phone(phone)
        if not user or not verify_password(user, password):
            log_attempt(phone, False)
            flash("Telefon raqami yoki parol noto‘g‘ri", "error")
            return render_template("auth/login.html", phone=phone)

        if user["status"] != "active":
            flash("Hisobingiz bloklangan. Qo‘llab-quvvatlash xizmatiga murojaat qiling", "error")
            return render_template("auth/login.html", phone=phone)

        log_attempt(phone, True)
        login(user, remember)
        audit(user["id"], "login")

        target = _safe_next(request.args.get("next") or request.form.get("next"))
        return redirect(target or url_for("cabinet.dashboard"))

    return render_template("auth/login.html", phone="")


# ------------------------------------------------------------------ ro'yxat
@bp.route("/royxatdan-otish", methods=["GET", "POST"])
@guest_only
def register_view():
    if get_setting("registration_open", "1") != "1":
        return render_template("auth/closed.html")

    if request.method == "POST":
        phone = normalize_phone(request.form.get("phone"))
        password = request.form.get("password") or ""
        name = (request.form.get("name") or "").strip()
        ref = (request.form.get("ref") or "").strip().upper()
        agree = request.form.get("agree")

        form = {"phone": request.form.get("phone"), "name": name, "ref": ref}

        if not phone:
            flash("Telefon raqamini to‘g‘ri kiriting", "error")
            return render_template("auth/register.html", **form)
        if len(password) < 6:
            flash("Parol kamida 6 ta belgidan iborat bo‘lsin", "error")
            return render_template("auth/register.html", **form)
        if password != request.form.get("password2"):
            flash("Parollar mos kelmadi", "error")
            return render_template("auth/register.html", **form)
        if not agree:
            flash("Ommaviy oferta shartlarini qabul qiling", "error")
            return render_template("auth/register.html", **form)

        referrer_id = None
        if ref:
            row = query("SELECT id FROM users WHERE ref_code = ?", (ref,), one=True)
            referrer_id = row["id"] if row else None

        try:
            user_id = create_user(phone, password, name, referrer_id)
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("auth/register.html", **form)

        user = query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
        login(user)
        audit(user_id, "register")
        flash("Xush kelibsiz! Birinchi profilingizni qo‘shing", "success")
        return redirect(url_for("cabinet.profiles"))

    return render_template("auth/register.html", phone="", name="",
                           ref=request.args.get("ref", ""))


# ------------------------------------------------------------------ chiqish
@bp.route("/chiqish", methods=["POST"])
def logout_view():
    user = current_user()
    if user:
        audit(user["id"], "logout")
    logout()
    flash("Tizimdan chiqdingiz", "info")
    return redirect(url_for("site.index"))


# ------------------------------------------------------------------ parol
@bp.route("/parolni-tiklash", methods=["GET", "POST"])
@guest_only
def reset_view():
    """Parolni tiklash — tasdiqlash kodi Telegram bot orqali yuboriladi.

    Bot tokeni sozlanmagan bo'lsa, kod ekranda ko'rsatiladi (dastlabki sozlash uchun).
    """
    step = session.get("reset_step", "phone")

    if request.method == "POST":
        action = request.form.get("action")

        if action == "send":
            phone = normalize_phone(request.form.get("phone"))
            if not phone:
                flash("Telefon raqamini to‘g‘ri kiriting", "error")
                return render_template("auth/reset.html", step="phone")

            user = get_user_by_phone(phone)
            if not user:
                flash("Bu raqam ro‘yxatdan o‘tmagan", "error")
                return render_template("auth/reset.html", step="phone")

            if rate_limited("reset:" + phone, limit=4, window_min=30):
                flash("Juda ko‘p urinish. Keyinroq urinib ko‘ring", "error")
                return render_template("auth/reset.html", step="phone")

            code = gen_code(5)
            session["reset_phone"] = phone
            session["reset_code"] = code
            session["reset_step"] = "code"
            log_attempt("reset:" + phone, False)

            sent = _send_reset_code(user, code)
            if not sent:
                flash("Tasdiqlash kodi: {} (bot sozlanmagani uchun ekranda "
                      "ko‘rsatildi)".format(code), "warning")
            else:
                flash("Tasdiqlash kodi Telegram orqali yuborildi", "success")
            return render_template("auth/reset.html", step="code", phone=phone)

        if action == "verify":
            code = "".join(request.form.getlist("code")).strip()
            if not session.get("reset_code") or code != session["reset_code"]:
                flash("Kod noto‘g‘ri", "error")
                return render_template("auth/reset.html", step="code",
                                       phone=session.get("reset_phone", ""))
            session["reset_step"] = "password"
            return render_template("auth/reset.html", step="password",
                                   phone=session.get("reset_phone", ""))

        if action == "save":
            password = request.form.get("password") or ""
            if len(password) < 6:
                flash("Parol kamida 6 ta belgidan iborat bo‘lsin", "error")
                return render_template("auth/reset.html", step="password")
            if password != request.form.get("password2"):
                flash("Parollar mos kelmadi", "error")
                return render_template("auth/reset.html", step="password")

            user = get_user_by_phone(session.get("reset_phone", ""))
            if not user:
                session.pop("reset_step", None)
                flash("Sessiya muddati tugadi. Qaytadan boshlang", "error")
                return redirect(url_for("auth.reset_view"))

            set_password(user["id"], password)
            audit(user["id"], "password_reset")
            for key in ("reset_step", "reset_code", "reset_phone"):
                session.pop(key, None)
            flash("Parol yangilandi. Endi tizimga kiring", "success")
            return redirect(url_for("auth.login_view"))

    return render_template("auth/reset.html", step=step,
                           phone=session.get("reset_phone", ""))


def _send_reset_code(user, code):
    """Kodni Telegram bot orqali yuborishga urinadi."""
    from config import config

    if not config.NOTIFY_BOT_TOKEN or not user["telegram_id"]:
        return False
    try:
        import requests

        resp = requests.post(
            "https://api.telegram.org/bot{}/sendMessage".format(config.NOTIFY_BOT_TOKEN),
            json={
                "chat_id": user["telegram_id"],
                "text": "🔐 AutoXabar parolni tiklash kodi: {}".format(code),
            },
            timeout=12,
        )
        return resp.ok
    except Exception:
        return False


# ------------------------------------------------------------------ parolni o'zgartirish
@bp.route("/parolni-ozgartirish", methods=["POST"])
@login_required
def change_password():
    user = current_user()
    current = request.form.get("current") or ""
    new = request.form.get("password") or ""

    if not verify_password(user, current):
        flash("Joriy parol noto‘g‘ri", "error")
    elif len(new) < 6:
        flash("Yangi parol kamida 6 ta belgidan iborat bo‘lsin", "error")
    elif new != request.form.get("password2"):
        flash("Parollar mos kelmadi", "error")
    else:
        set_password(user["id"], new)
        audit(user["id"], "password_change")
        flash("Parol yangilandi", "success")

    return redirect(url_for("cabinet.settings"))
