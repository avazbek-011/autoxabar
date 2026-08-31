"""Administrator paneli: umumiy ko'rinish, moliya, foydalanuvchilar, sozlamalar."""
from datetime import timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from config import config
from core.auth import admin_required, current_user
from core.db import (
    execute,
    get_setting,
    month_str,
    now,
    now_str,
    query,
    scalar,
    set_setting,
    today_str,
    update,
)
from core.utils import audit, notify, safe_int
from services import billing, scheduler, worker
from services import finance as fin
from services import telegram_engine as tg

bp = Blueprint("admin", __name__)


@bp.before_request
@admin_required
def guard():
    """Barcha admin sahifalari uchun ruxsat tekshiruvi."""
    return None


# ==================================================================== panel
@bp.route("/")
def dashboard():
    today = today_str()
    month = month_str()

    users_total = scalar("SELECT COUNT(*) FROM users WHERE role = 'user'")
    users_today = scalar(
        "SELECT COUNT(*) FROM users WHERE role = 'user' AND created_at LIKE ?",
        (today + "%",),
    )
    profiles_total = scalar("SELECT COUNT(*) FROM profiles")
    profiles_running = scalar("SELECT COUNT(*) FROM profiles WHERE status = 'running'")
    profiles_pro = scalar(
        "SELECT COUNT(*) FROM profiles WHERE plan = 'pro' AND expires_at > ?", (now_str(),)
    )

    today_rev = fin.today_revenue()
    month_rep = fin.month_report(month)
    all_time = fin.totals()

    sent_total = scalar("SELECT COALESCE(SUM(sent_total), 0) FROM profiles")
    sent_24h = scalar("SELECT COALESCE(SUM(sent_24h), 0) FROM profiles")

    chart = [
        {"label": d["label"], "value": d["gross"]}
        for d in fin.daily_series(30)
    ]

    recent_payments = query(
        "SELECT pm.*, u.phone, u.name FROM payments pm JOIN users u ON u.id = pm.user_id "
        "WHERE pm.status = 'paid' ORDER BY pm.id DESC LIMIT 10"
    )
    recent_users = query(
        "SELECT * FROM users WHERE role = 'user' ORDER BY id DESC LIMIT 8"
    )

    problems = query(
        "SELECT p.*, u.phone AS uphone FROM profiles p JOIN users u ON u.id = p.user_id "
        "WHERE p.status IN ('error', 'banned') ORDER BY p.updated_at DESC LIMIT 10"
    )

    return render_template(
        "admin/dashboard.html",
        users_total=users_total,
        users_today=users_today,
        profiles_total=profiles_total,
        profiles_running=profiles_running,
        profiles_pro=profiles_pro,
        today_rev=today_rev,
        month_rep=month_rep,
        all_time=all_time,
        sent_total=sent_total,
        sent_24h=sent_24h,
        chart=chart,
        recent_payments=recent_payments,
        recent_users=recent_users,
        problems=problems,
    )


# ==================================================================== moliya
@bp.route("/moliya")
def finance():
    month = request.args.get("month") or month_str()
    report = fin.month_report(month)
    totals = fin.totals()
    months = fin.known_months()
    series = fin.monthly_series(12)
    daily = fin.daily_series(30)

    ledger = fin.ledger_list(month, limit=200)
    payouts = fin.payouts_list(60)
    expenses = fin.expenses_list(month, 60)

    chart_monthly = [{"label": s["short"], "value": s["net"]} for s in series]
    chart_daily = [{"label": d["label"], "value": d["gross"]} for d in daily]

    # Prognoz: faol avto-obunalar bo'yicha keyingi oy tushumi
    active_subs = scalar(
        "SELECT COUNT(*) FROM subscriptions WHERE status = 'active' AND auto_renew = 1"
    )
    forecast_gross = active_subs * billing.price()
    forecast = fin.split(forecast_gross)

    return render_template(
        "admin/finance.html",
        month=month,
        months=months,
        report=report,
        totals=totals,
        series=series,
        ledger=ledger,
        payouts=payouts,
        expenses=expenses,
        chart_monthly=chart_monthly,
        chart_daily=chart_daily,
        forecast=forecast,
        active_subs=active_subs,
        categories=fin.EXPENSE_CATEGORIES,
        bank_name=get_setting("bank_name", ""),
        bank_account=get_setting("bank_account", ""),
    )



@bp.route("/moliya/yechim", methods=["POST"])
def payout_add():
    user = current_user()
    month = request.form.get("month") or month_str()
    amount = safe_int(request.form.get("amount"), 0, 0)
    kind = request.form.get("kind") or "net"
    destination = (request.form.get("destination") or "").strip()[:120]
    note = (request.form.get("note") or "").strip()[:250]

    if amount <= 0:
        flash("Summani kiriting", "error")
        return redirect(url_for("admin.finance", month=month))

    report = fin.month_report(month)
    limit = report["remaining_net"] if kind == "net" else report["remaining_tax"]
    if amount > limit and not request.form.get("force"):
        flash(
            "Kiritilgan summa mavjud qoldiqdan ({}) katta. Tasdiqlash uchun "
            "«Baribir yozish» belgisini qo‘ying".format(limit),
            "error",
        )
        return redirect(url_for("admin.finance", month=month))

    fin.add_payout(month, amount, kind, destination, note, user["id"])
    audit(user["id"], "payout", month, {"amount": amount, "kind": kind})
    flash("Yechib olish qayd etildi", "success")
    return redirect(url_for("admin.finance", month=month))


@bp.route("/moliya/yechim/<int:payout_id>/ochirish", methods=["POST"])
def payout_delete(payout_id):
    row = query("SELECT * FROM payouts WHERE id = ?", (payout_id,), one=True)
    execute("DELETE FROM payouts WHERE id = ?", (payout_id,))
    flash("Yozuv o‘chirildi", "info")
    return redirect(url_for("admin.finance", month=row["month"] if row else month_str()))


@bp.route("/moliya/chiqim", methods=["POST"])
def expense_add():
    user = current_user()
    month = request.form.get("month") or month_str()
    amount = safe_int(request.form.get("amount"), 0, 0)
    title = (request.form.get("title") or "").strip()[:120]
    category = request.form.get("category") or "other"
    note = (request.form.get("note") or "").strip()[:250]

    if amount <= 0 or not title:
        flash("Nomi va summasini kiriting", "error")
        return redirect(url_for("admin.finance", month=month))

    day = request.form.get("day") or today_str()
    fin.add_expense(category, title, amount, note, day)
    audit(user["id"], "expense", title, {"amount": amount})
    flash("Chiqim qo‘shildi", "success")
    return redirect(url_for("admin.finance", month=month))


@bp.route("/moliya/chiqim/<int:expense_id>/ochirish", methods=["POST"])
def expense_delete(expense_id):
    row = query("SELECT * FROM expenses WHERE id = ?", (expense_id,), one=True)
    execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    flash("Chiqim o‘chirildi", "info")
    return redirect(url_for("admin.finance", month=row["month"] if row else month_str()))


@bp.route("/moliya/qayta-hisoblash", methods=["POST"])
def finance_rebuild():
    count = fin.rebuild_ledger()
    flash("Moliya daftari yangilandi: {} ta yozuv qo‘shildi".format(count), "success")
    return redirect(url_for("admin.finance"))


# ==================================================================== to'lovlar
@bp.route("/tolovlar")
def payments():
    status = request.args.get("status", "")
    page = safe_int(request.args.get("page"), 1, 1)
    per_page = 50

    where, params = [], []
    if status:
        where.append("pm.status = ?")
        params.append(status)

    clause = ("WHERE " + " AND ".join(where)) if where else ""
    total = scalar("SELECT COUNT(*) FROM payments pm " + clause, tuple(params))

    rows = query(
        "SELECT pm.*, u.phone, u.name, p.title AS ptitle FROM payments pm "
        "JOIN users u ON u.id = pm.user_id "
        "LEFT JOIN profiles p ON p.id = pm.profile_id " + clause +
        " ORDER BY pm.id DESC LIMIT ? OFFSET ?",
        tuple(params) + (per_page, (page - 1) * per_page),
    )

    return render_template(
        "admin/payments.html",
        payments=rows,
        status=status,
        page=page,
        pages=max(1, (total + per_page - 1) // per_page),
        total=total,
    )


@bp.route("/tolov/<int:payment_id>/qolda", methods=["POST"])
def payment_manual(payment_id):
    """To'lovni qo'lda tasdiqlash (masalan, bank o'tkazmasi)."""
    payment = query("SELECT * FROM payments WHERE id = ?", (payment_id,), one=True)
    if not payment:
        flash("To‘lov topilmadi", "error")
    elif payment["status"] == "paid":
        flash("Bu to‘lov allaqachon tasdiqlangan", "warning")
    else:
        billing.mark_paid(payment_id, external_id="manual")
        audit(current_user()["id"], "payment_manual", payment_id)
        flash("To‘lov tasdiqlandi", "success")
    return redirect(url_for("admin.payments"))


# ==================================================================== foydalanuvchilar
@bp.route("/foydalanuvchilar")
def users():
    q = (request.args.get("q") or "").strip()
    page = safe_int(request.args.get("page"), 1, 1)
    per_page = 40

    where, params = ["1 = 1"], []
    if q:
        where.append("(u.phone LIKE ? OR u.name LIKE ?)")
        params += ["%" + q + "%", "%" + q + "%"]

    clause = " AND ".join(where)
    total = scalar("SELECT COUNT(*) FROM users u WHERE " + clause, tuple(params))

    rows = query(
        "SELECT u.*, (SELECT COUNT(*) FROM profiles p WHERE p.user_id = u.id) AS profiles, "
        "(SELECT COALESCE(SUM(amount),0) FROM payments pm WHERE pm.user_id = u.id "
        "AND pm.status = 'paid') AS paid "
        "FROM users u WHERE " + clause + " ORDER BY u.id DESC LIMIT ? OFFSET ?",
        tuple(params) + (per_page, (page - 1) * per_page),
    )

    return render_template(
        "admin/users.html",
        users=rows,
        q=q,
        page=page,
        pages=max(1, (total + per_page - 1) // per_page),
        total=total,
    )


@bp.route("/foydalanuvchi/<int:user_id>")
def user_detail(user_id):
    row = query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    if not row:
        flash("Foydalanuvchi topilmadi", "error")
        return redirect(url_for("admin.users"))

    profiles = query("SELECT * FROM profiles WHERE user_id = ? ORDER BY id DESC", (user_id,))
    payments = query(
        "SELECT * FROM payments WHERE user_id = ? ORDER BY id DESC LIMIT 40", (user_id,)
    )
    paid = scalar(
        "SELECT COALESCE(SUM(amount),0) FROM payments WHERE user_id = ? AND status='paid'",
        (user_id,),
    )
    return render_template(
        "admin/user_detail.html",
        u=row,
        profiles=profiles,
        payments=payments,
        paid=paid,
    )


@bp.route("/foydalanuvchi/<int:user_id>/amal", methods=["POST"])
def user_action(user_id):
    admin = current_user()
    action = request.form.get("action")
    row = query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    if not row:
        flash("Foydalanuvchi topilmadi", "error")
        return redirect(url_for("admin.users"))

    if row["id"] == admin["id"] and action in ("block", "demote"):
        flash("O‘zingizga nisbatan bu amalni bajarib bo‘lmaydi", "error")
        return redirect(url_for("admin.user_detail", user_id=user_id))

    if action == "block":
        update("users", {"status": "blocked", "updated_at": now_str()}, "id = ?", (user_id,))
        execute(
            "UPDATE profiles SET status = 'paused', status_note = 'Hisob bloklangan' "
            "WHERE user_id = ? AND status = 'running'",
            (user_id,),
        )
        flash("Foydalanuvchi bloklandi", "warning")

    elif action == "unblock":
        update("users", {"status": "active", "updated_at": now_str()}, "id = ?", (user_id,))
        flash("Blok olib tashlandi", "success")

    elif action == "promote":
        update("users", {"role": "admin", "updated_at": now_str()}, "id = ?", (user_id,))
        flash("Administrator huquqi berildi", "success")

    elif action == "demote":
        update("users", {"role": "user", "updated_at": now_str()}, "id = ?", (user_id,))
        flash("Administrator huquqi olib tashlandi", "info")

    elif action == "balance":
        amount = safe_int(request.form.get("amount"), 0)
        execute(
            "UPDATE users SET balance = balance + ?, updated_at = ? WHERE id = ?",
            (amount, now_str(), user_id),
        )
        notify(
            user_id,
            "Balans o‘zgardi",
            "Administrator hisobingizga {} so‘m qo‘shdi.".format(amount),
            "info",
        )
        flash("Balans yangilandi", "success")

    elif action == "gift":
        days = safe_int(request.form.get("days"), 30, 1, 365)
        profile_id = safe_int(request.form.get("profile_id"), 0)
        if profile_id:
            billing.extend_subscription(user_id, profile_id, days=days, amount=0)
            flash("{} kunlik obuna berildi".format(days), "success")
        else:
            flash("Profilni tanlang", "error")

    elif action == "note":
        update(
            "users",
            {"notes": (request.form.get("notes") or "")[:1000], "updated_at": now_str()},
            "id = ?",
            (user_id,),
        )
        flash("Izoh saqlandi", "success")

    audit(admin["id"], "user_" + str(action), user_id)
    return redirect(url_for("admin.user_detail", user_id=user_id))


# ==================================================================== profillar
@bp.route("/profillar")
def profiles():
    status = request.args.get("status", "")
    where = "WHERE p.status = ?" if status else ""
    params = (status,) if status else ()

    rows = query(
        "SELECT p.*, u.phone AS uphone, u.name AS uname FROM profiles p "
        "JOIN users u ON u.id = p.user_id " + where +
        " ORDER BY p.sent_24h DESC, p.id DESC LIMIT 200",
        params,
    )

    counts = {
        r["status"]: r["c"]
        for r in query("SELECT status, COUNT(*) AS c FROM profiles GROUP BY status")
    }
    return render_template(
        "admin/profiles.html", profiles=rows, status=status, counts=counts
    )


@bp.route("/profil/<int:profile_id>/amal", methods=["POST"])
def profile_action(profile_id):
    action = request.form.get("action")
    if action == "stop":
        worker.stop_profile(profile_id, "Administrator to‘xtatdi")
        flash("Profil to‘xtatildi", "info")
    elif action == "start":
        ok, message = worker.start_profile(profile_id)
        flash(message, "success" if ok else "error")
    elif action == "delete":
        execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        flash("Profil o‘chirildi", "info")
    audit(current_user()["id"], "admin_profile_" + str(action), profile_id)
    return redirect(request.referrer or url_for("admin.profiles"))


# ==================================================================== sozlamalar
@bp.route("/sozlamalar", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        fields = {
            "price_per_profile": safe_int(request.form.get("price_per_profile"), 5000, 0),
            "tax_percent": request.form.get("tax_percent") or "10",
            "acquiring_percent": request.form.get("acquiring_percent") or "1",
            "trial_days": safe_int(request.form.get("trial_days"), 3, 0, 90),
            "max_profiles_per_user": safe_int(
                request.form.get("max_profiles_per_user"), 10, 1, 500
            ),
            "telegram_engine": (request.form.get("telegram_engine") or "auto"),
            "registration_open": "1" if request.form.get("registration_open") else "0",
            "free_plan_enabled": "1" if request.form.get("free_plan_enabled") else "0",
            "site_open": "1" if request.form.get("site_open") else "0",
            "announce": (request.form.get("announce") or "")[:500],
            "bank_name": (request.form.get("bank_name") or "")[:120],
            "bank_account": (request.form.get("bank_account") or "")[:60],
        }
        try:
            float(fields["tax_percent"])
            float(fields["acquiring_percent"])
        except ValueError:
            flash("Foizlarni raqam ko‘rinishida kiriting", "error")
            return redirect(url_for("admin.settings"))

        if fields["telegram_engine"] not in ("auto", "real", "demo"):
            fields["telegram_engine"] = "auto"

        for key, value in fields.items():
            set_setting(key, value)

        tg.reset_mode_cache()

        audit(current_user()["id"], "settings_update")
        flash("Sozlamalar saqlandi", "success")
        return redirect(url_for("admin.settings"))

    keys = [
        "price_per_profile", "tax_percent", "acquiring_percent", "trial_days",
        "max_profiles_per_user", "registration_open", "free_plan_enabled",
        "site_open", "announce", "bank_name", "bank_account", "telegram_engine",
    ]
    values = {key: get_setting(key, "") for key in keys}
    if not values.get("telegram_engine"):
        values["telegram_engine"] = "auto"
    return render_template("admin/settings.html", s=values, engine=tg.engine_mode())


# ==================================================================== tizim
@bp.route("/tizim")
def system():
    counts = {
        "users": scalar("SELECT COUNT(*) FROM users"),
        "profiles": scalar("SELECT COUNT(*) FROM profiles"),
        "groups": scalar("SELECT COUNT(*) FROM groups"),
        "ads": scalar("SELECT COUNT(*) FROM ads"),
        "payments": scalar("SELECT COUNT(*) FROM payments"),
        "send_log": scalar("SELECT COUNT(*) FROM send_log"),
        "cards": scalar("SELECT COUNT(*) FROM cards WHERE status = 'active'"),
        "subscriptions": scalar(
            "SELECT COUNT(*) FROM subscriptions WHERE status = 'active'"
        ),
    }

    errors = query(
        "SELECT error, COUNT(*) AS c FROM send_log WHERE status = 'fail' "
        "AND created_at > ? GROUP BY error ORDER BY c DESC LIMIT 12",
        ((now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),),
    )

    audit_rows = query(
        "SELECT a.*, u.phone FROM audit_log a LEFT JOIN users u ON u.id = a.user_id "
        "ORDER BY a.id DESC LIMIT 40"
    )

    import os

    db_size = 0
    try:
        db_size = os.path.getsize(config.DB_PATH)
    except OSError:
        pass

    return render_template(
        "admin/system.html",
        counts=counts,
        errors=errors,
        audit_rows=audit_rows,
        jobs=scheduler.jobs(),
        scheduler_running=scheduler.is_running(),
        engine=tg.engine_mode(),
        telethon=tg.TELETHON_AVAILABLE,
        db_size=db_size,
        payme_merchant=bool(config.PAYME_MERCHANT_ID and config.PAYME_KEY),
        payme_subscribe=bool(config.PAYME_SUBSCRIBE_ID and config.PAYME_SUBSCRIBE_KEY),
        merchant_url=config.BASE_URL + "/api/payme",
    )


@bp.route("/tizim/amal", methods=["POST"])
def system_action():
    action = request.form.get("action")
    if action == "tick":
        started = worker.tick()
        flash("{} ta profil sikli ishga tushirildi".format(started), "success")
    elif action == "counters":
        worker.refresh_counters()
        flash("Hisoblagichlar yangilandi", "success")
    elif action == "charge":
        ok, fail = billing.charge_due_subscriptions()
        flash("Avto-to‘lov: {} muvaffaqiyatli, {} xato".format(ok, fail), "info")
    elif action == "expire":
        count = billing.expire_overdue()
        flash("{} ta obuna yopildi".format(count), "info")
    elif action == "cleanup":
        worker.cleanup_logs()
        flash("Eski jurnallar tozalandi", "success")
    audit(current_user()["id"], "system_" + str(action))
    return redirect(url_for("admin.system"))
