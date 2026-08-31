"""Foydalanuvchi kabineti: profillar, xabarlar, guruhlar, statistika, to'lovlar."""
import logging
import os
import uuid
from datetime import timedelta

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from config import config
from core.auth import current_user, login_required, own_ad_or_404, own_profile_or_404
from core.db import (
    execute,
    get_setting,
    get_setting_int,
    set_setting,
    now,
    now_str,
    query,
    scalar,
    update,
)
from core.utils import (
    audit,
    human_seconds,
    dt_str,
    normalize_phone,
    notify,
    num,
    safe_int,
    sanitize_ad_html,
)
from services import billing as billing_svc
from services import worker
from services import telegram_engine as tg
from services.payme import checkout_url, subscribe_api

log = logging.getLogger("cabinet")

bp = Blueprint("cabinet", __name__)

ALLOWED_IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


# ==================================================================== panel
@bp.route("/")
@login_required
def dashboard():
    user = current_user()
    uid = user["id"]

    profiles = query(
        "SELECT * FROM profiles WHERE user_id = ? ORDER BY id DESC", (uid,)
    )
    running = sum(1 for p in profiles if p["status"] == "running")
    sent_total = sum(p["sent_total"] for p in profiles)
    sent_24h = sum(p["sent_24h"] for p in profiles)
    groups = scalar(
        "SELECT COUNT(*) FROM groups g JOIN profiles p ON p.id = g.profile_id "
        "WHERE p.user_id = ? AND g.enabled = 1",
        (uid,),
    )

    # Oxirgi 14 kunlik grafik
    frm = (now() - timedelta(days=13)).strftime("%Y-%m-%d")
    rows = query(
        "SELECT day, SUM(sent) AS sent FROM stats_daily WHERE user_id = ? AND day >= ? "
        "GROUP BY day",
        (uid, frm),
    )
    by_day = {r["day"]: r["sent"] for r in rows}
    chart = []
    for i in range(14):
        day = (now() - timedelta(days=13 - i)).strftime("%Y-%m-%d")
        chart.append({"label": day[8:10] + "." + day[5:7], "value": by_day.get(day, 0)})

    recent = query(
        "SELECT s.*, p.title AS ptitle, p.phone AS pphone FROM send_log s "
        "JOIN profiles p ON p.id = s.profile_id WHERE p.user_id = ? "
        "ORDER BY s.id DESC LIMIT 12",
        (uid,),
    )

    next_expiry = query(
        "SELECT * FROM profiles WHERE user_id = ? AND expires_at IS NOT NULL "
        "AND expires_at > ? ORDER BY expires_at ASC LIMIT 1",
        (uid, now_str()),
        one=True,
    )

    return render_template(
        "cabinet/dashboard.html",
        profiles=profiles,
        running=running,
        sent_total=sent_total,
        sent_24h=sent_24h,
        groups=groups,
        chart=chart,
        recent=recent,
        next_expiry=next_expiry,
        ads_count=scalar("SELECT COUNT(*) FROM ads WHERE user_id = ?", (uid,)),
    )


@bp.route("/api/live")
@login_required
def api_live():
    uid = current_user()["id"]
    row = query(
        "SELECT COALESCE(SUM(sent_total),0) AS total, COALESCE(SUM(sent_24h),0) AS d24, "
        "SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running "
        "FROM profiles WHERE user_id = ?",
        (uid,),
        one=True,
    )
    return jsonify(
        ok=True,
        values={
            "sent_total": num(row["total"]),
            "sent_24h": num(row["d24"]),
            "running": num(row["running"] or 0),
        },
    )


# ---------------------------------------------------- Akkaunt chegarasi
def profile_limit():
    """Foydalanuvchi ulashi mumkin bo'lgan akkauntlar soni. 0 = cheksiz."""
    return get_setting_int("max_profiles_per_user", 50)


def limit_reached(user_id):
    """Chegaraga yetdimi? (limit, hozirgi_son, yetdimi)"""
    limit = profile_limit()
    count = scalar("SELECT COUNT(*) FROM profiles WHERE user_id = ?", (user_id,))
    if limit <= 0:                      # 0 yoki manfiy = cheksiz
        return 0, count, False
    return limit, count, count >= limit


# ---------------------------------------------------- Telegram cheklovi
def _flood_key(phone):
    return "tgflood:" + phone


def flood_left(phone):
    """Shu raqam uchun qolgan cheklov vaqti (soniya). 0 — cheklov yo'q."""
    import time as _time

    try:
        until = float(get_setting(_flood_key(phone), 0) or 0)
    except (TypeError, ValueError):
        return 0
    left = int(until - _time.time())
    return left if left > 0 else 0


def set_flood(phone, seconds):
    import time as _time

    if seconds > 0:
        set_setting(_flood_key(phone), str(int(_time.time()) + int(seconds)))


# ==================================================================== profillar
@bp.route("/profillar")
@login_required
def profiles():
    uid = current_user()["id"]
    rows = query(
        "SELECT p.*, a.title AS ad_title FROM profiles p "
        "LEFT JOIN ads a ON a.id = p.active_ad_id "
        "WHERE p.user_id = ? ORDER BY p.id DESC",
        (uid,),
    )
    limit, count, reached = limit_reached(uid)
    return render_template(
        "cabinet/profiles.html",
        profiles=rows,
        limit=limit,
        can_add=not reached,
        demo=tg.is_demo(),
        connect=session.get("tg_connect"),
    )


@bp.route("/profillar/ulash", methods=["POST"])
@login_required
def profile_connect():
    """1-qadam: telefon raqamiga Telegram kodi yuboriladi."""
    user = current_user()
    limit, count, reached = limit_reached(user["id"])
    if reached:
        flash("Akkauntlar chegarasiga yetdingiz ({} ta). Administrator "
              "chegarani oshirishi mumkin".format(limit), "error")
        return redirect(url_for("cabinet.profiles"))

    phone = normalize_phone(request.form.get("phone"))
    if not phone:
        flash("Telefon raqamini to‘g‘ri kiriting", "error")
        return redirect(url_for("cabinet.profiles"))

    exists = query(
        "SELECT 1 FROM profiles WHERE phone = ? AND status != 'error'", (phone,), one=True
    )
    if exists:
        flash("Bu raqam allaqachon ulangan", "error")
        return redirect(url_for("cabinet.profiles"))

    # Telegram bu raqamni cheklagan bo'lsa, qayta so'rov yubormaymiz —
    # har bir urinish cheklov muddatini yana uzaytiradi.
    left = flood_left(phone)
    if left > 0:
        flash(
            "Telegram bu raqamni vaqtincha cheklagan. Yana {} kutish kerak. "
            "Boshqa raqam bilan sinab ko'rishingiz mumkin".format(human_seconds(left)),
            "warning",
        )
        return redirect(url_for("cabinet.profiles"))

    try:
        token = tg.send_login_code(phone)
    except tg.TgError as exc:
        set_flood(phone, getattr(exc, "wait", 0))
        flash(str(exc), "error")
        return redirect(url_for("cabinet.profiles"))
    except Exception as exc:
        log.exception("Kod yuborishda kutilmagan xato")
        flash("Telegram bilan bog‘lanib bo‘lmadi: {}".format(str(exc)[:150]), "error")
        return redirect(url_for("cabinet.profiles"))

    session["tg_connect"] = {"token": token, "phone": phone, "stage": "code"}
    flash("Telegram ilovangizga kod yuborildi", "success")
    return redirect(url_for("cabinet.profiles"))


@bp.route("/profillar/kod", methods=["POST"])
@login_required
def profile_code():
    """2-qadam: kodni tasdiqlash."""
    user = current_user()
    conn = session.get("tg_connect")
    if not conn:
        flash("Sessiya muddati tugadi. Qaytadan boshlang", "error")
        return redirect(url_for("cabinet.profiles"))

    # Kod 5 ta alohida katakdan keladi (hammasining nomi "code")
    code = "".join(request.form.getlist("code")).strip()

    try:
        status, info = tg.confirm_login_code(conn["token"], code)
    except tg.TgError as exc:
        message = str(exc)
        wait = getattr(exc, "wait", 0)
        if wait:
            set_flood(conn["phone"], wait)
            session.pop("tg_connect", None)
        flash(message, "error")
        # Sessiya yaroqsiz bo'lsa, qaytadan boshlash uchun tozalaymiz
        if "qaytadan boshlang" in message:
            session.pop("tg_connect", None)
        return redirect(url_for("cabinet.profiles"))
    except Exception as exc:
        log.exception("Kodni tasdiqlashda kutilmagan xato")
        session.pop("tg_connect", None)
        flash("Ulanishda xatolik: {}. Qaytadan boshlang".format(str(exc)[:120]), "error")
        return redirect(url_for("cabinet.profiles"))

    if status == "password":
        conn["stage"] = "password"
        session["tg_connect"] = conn
        flash("Ikki bosqichli parolni kiriting", "info")
        return redirect(url_for("cabinet.profiles"))

    return _finish_connect(user, conn, info)


@bp.route("/profillar/parol", methods=["POST"])
@login_required
def profile_password():
    """3-qadam: 2FA paroli."""
    user = current_user()
    conn = session.get("tg_connect")
    if not conn:
        flash("Sessiya muddati tugadi. Qaytadan boshlang", "error")
        return redirect(url_for("cabinet.profiles"))

    try:
        info = tg.confirm_login_password(conn["token"], request.form.get("password") or "")
    except tg.TgError as exc:
        flash(str(exc), "error")
        return redirect(url_for("cabinet.profiles"))
    except Exception as exc:
        log.exception("2FA parolida kutilmagan xato")
        session.pop("tg_connect", None)
        flash("Ulanishda xatolik: {}. Qaytadan boshlang".format(str(exc)[:120]), "error")
        return redirect(url_for("cabinet.profiles"))

    return _finish_connect(user, conn, info)


@bp.route("/profillar/bekor", methods=["POST"])
@login_required
def profile_connect_cancel():
    conn = session.pop("tg_connect", None)
    if conn:
        tg.login_store.drop(conn["token"])
    return redirect(url_for("cabinet.profiles"))



# ---------------------------------------------------------------- QR ulash
@bp.route("/profillar/qr", methods=["POST"])
@login_required
def profile_qr_start():
    """QR orqali ulashni boshlaydi."""
    user = current_user()
    limit, count, reached = limit_reached(user["id"])
    if reached:
        flash("Akkauntlar chegarasiga yetdingiz ({} ta). Administrator "
              "chegarani oshirishi mumkin".format(limit), "error")
        return redirect(url_for("cabinet.profiles"))

    try:
        token = tg.start_qr_login()
    except tg.TgError as exc:
        flash(str(exc), "error")
        return redirect(url_for("cabinet.profiles"))
    except Exception as exc:
        log.exception("QR boshlashda xato")
        flash("QR kod yaratilmadi: {}".format(str(exc)[:120]), "error")
        return redirect(url_for("cabinet.profiles"))

    session["tg_connect"] = {"token": token, "phone": "", "stage": "qr", "qr": True}
    return redirect(url_for("cabinet.profiles") + "#qr")


@bp.route("/profillar/qr/rasm")
@login_required
def profile_qr_image():
    """QR kod rasmi (PNG)."""
    conn = session.get("tg_connect") or {}
    if not conn.get("qr"):
        abort(404)
    png = tg.qr_png(conn["token"])
    resp = make_response(png)
    resp.headers["Content-Type"] = "image/png"
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


@bp.route("/profillar/qr/holat")
@login_required
def profile_qr_status():
    """Brauzer har 2 soniyada shu manzilni so'raydi."""
    conn = session.get("tg_connect") or {}
    if not conn.get("qr"):
        return jsonify(status="expired")

    state = tg.qr_status(conn["token"])

    if state["status"] == "ok":
        info = tg.qr_info(conn["token"])
        if info:
            user = current_user()
            profile_id = _create_profile(user, info.get("phone") or "QR", info)
            tg.login_store.drop(conn["token"], disconnect=False)
            session.pop("tg_connect", None)
            return jsonify(status="ok",
                           redirect=url_for("cabinet.profile_detail", profile_id=profile_id))
        return jsonify(status="waiting")

    if state["status"] == "password":
        conn["stage"] = "password"
        session["tg_connect"] = conn
        return jsonify(status="password", redirect=url_for("cabinet.profiles"))

    if state["status"] in ("expired", "error"):
        session.pop("tg_connect", None)
        return jsonify(status=state["status"], error=state.get("error", ""))

    return jsonify(status="waiting")

def _finish_connect(user, conn, info):
    """Ulanish yakuni: profil yaratiladi va guruhlar o'qiladi."""
    session.pop("tg_connect", None)

    if not info or not info.get("session"):
        flash("Telegram sessiyasi olinmadi. Qaytadan urinib ko‘ring", "error")
        return redirect(url_for("cabinet.profiles"))

    profile_id = _create_profile(user, conn["phone"], info)
    return redirect(url_for("cabinet.profile_detail", profile_id=profile_id))


def _create_profile(user, phone, info):
    """Profil yozuvini yaratadi, sinov muddatini beradi va guruhlarni o'qiydi."""
    title = info.get("first_name") or info.get("username") or phone
    profile_id = execute(
        "INSERT INTO profiles(user_id, title, phone, tg_user_id, tg_username, "
        "tg_first_name, session_string, status, interval_min, smart_rest, "
        "created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            user["id"],
            title[:60],
            info.get("phone") or phone,
            info.get("tg_user_id", ""),
            info.get("username", ""),
            info.get("first_name", ""),
            info.get("session", ""),
            "connected",
            10,
            1,
            now_str(),
            now_str(),
        ),
    )

    # Bepul sinov muddati
    billing_svc.start_trial(user["id"], profile_id)

    # Guruh va kanallarni darhol o'qib olamiz
    try:
        added = _sync_groups(profile_id, info.get("session", ""))
        flash("Profil ulandi. {} ta guruh topildi".format(added), "success")
    except Exception as exc:
        log.warning("Guruhlarni o'qishda xato: %s", exc)
        flash("Profil ulandi. Guruhlarni «Yangilash» tugmasi bilan yuklang", "warning")

    audit(user["id"], "profile_connect", profile_id, {"phone": phone})
    return profile_id


def _sync_groups(profile_id, session_string):
    """Telegram'dan guruhlar ro'yxatini yangilaydi."""
    groups = tg.fetch_groups(session_string)
    added = 0
    for grp in groups:
        exists = query(
            "SELECT id FROM groups WHERE profile_id = ? AND chat_id = ?",
            (profile_id, grp["chat_id"]),
            one=True,
        )
        if exists:
            execute(
                "UPDATE groups SET title = ?, username = ?, members = ? WHERE id = ?",
                (grp["title"], grp["username"], grp["members"], exists["id"]),
            )
        else:
            execute(
                "INSERT INTO groups(profile_id, chat_id, title, username, members, "
                "enabled, created_at) VALUES(?,?,?,?,?,?,?)",
                (
                    profile_id,
                    grp["chat_id"],
                    grp["title"],
                    grp["username"],
                    grp["members"],
                    1,
                    now_str(),
                ),
            )
            added += 1

    count = scalar(
        "SELECT COUNT(*) FROM groups WHERE profile_id = ? AND enabled = 1", (profile_id,)
    )
    update(
        "profiles",
        {"groups_count": count, "updated_at": now_str()},
        "id = ?",
        (profile_id,),
    )
    return added


@bp.route("/profil/<int:profile_id>")
@login_required
def profile_detail(profile_id):
    profile = own_profile_or_404(profile_id)
    uid = current_user()["id"]

    groups = query(
        "SELECT * FROM groups WHERE profile_id = ? ORDER BY enabled DESC, "
        "members DESC, title",
        (profile_id,),
    )
    ads = query(
        "SELECT * FROM ads WHERE user_id = ? AND is_active = 1 ORDER BY id DESC", (uid,)
    )
    sub = billing_svc.get_subscription(profile_id)
    logs = query(
        "SELECT * FROM send_log WHERE profile_id = ? ORDER BY id DESC LIMIT 40",
        (profile_id,),
    )

    frm = (now() - timedelta(days=13)).strftime("%Y-%m-%d")
    rows = query(
        "SELECT day, sent FROM stats_daily WHERE profile_id = ? AND day >= ? ORDER BY day",
        (profile_id, frm),
    )
    by_day = {r["day"]: r["sent"] for r in rows}
    chart = []
    for i in range(14):
        day = (now() - timedelta(days=13 - i)).strftime("%Y-%m-%d")
        chart.append({"label": day[8:10] + "." + day[5:7], "value": by_day.get(day, 0)})

    return render_template(
        "cabinet/profile_detail.html",
        profile=profile,
        groups=groups,
        ads=ads,
        sub=sub,
        logs=logs,
        chart=chart,
        intervals=config.INTERVALS,
        enabled_count=sum(1 for g in groups if g["enabled"]),
    )


@bp.route("/profil/<int:profile_id>/sozlash", methods=["POST"])
@login_required
def profile_update(profile_id):
    own_profile_or_404(profile_id)

    title = (request.form.get("title") or "").strip()[:60]
    interval = safe_int(request.form.get("interval"), 10)
    if interval not in config.INTERVALS:
        interval = 10
    ad_id = safe_int(request.form.get("ad_id"), 0)

    if ad_id:
        own_ad_or_404(ad_id)

    update(
        "profiles",
        {
            "title": title,
            "interval_min": interval,
            "smart_rest": 1 if request.form.get("smart_rest") else 0,
            "active_ad_id": ad_id or None,
            "updated_at": now_str(),
        },
        "id = ?",
        (profile_id,),
    )
    flash("Sozlamalar saqlandi", "success")
    return redirect(url_for("cabinet.profile_detail", profile_id=profile_id))


@bp.route("/profil/<int:profile_id>/holat", methods=["POST"])
@login_required
def profile_toggle(profile_id):
    profile = own_profile_or_404(profile_id)
    action = request.form.get("action")

    if action == "start":
        ok, message = worker.start_profile(profile_id)
        flash(message, "success" if ok else "error")
        if ok:
            audit(current_user()["id"], "profile_start", profile_id)
    else:
        worker.stop_profile(profile_id)
        flash("Profil to‘xtatildi", "info")
        audit(current_user()["id"], "profile_stop", profile_id)

    back = request.form.get("back")
    if back == "list":
        return redirect(url_for("cabinet.profiles"))
    return redirect(url_for("cabinet.profile_detail", profile_id=profile_id))


@bp.route("/profil/<int:profile_id>/guruhlar/yangilash", methods=["POST"])
@login_required
def profile_sync_groups(profile_id):
    profile = own_profile_or_404(profile_id)
    try:
        added = _sync_groups(profile_id, profile["session_string"])
        flash("Guruhlar yangilandi. {} ta yangi guruh qo‘shildi".format(added), "success")
    except tg.TgError as exc:
        flash(str(exc), "error")
    except Exception as exc:
        flash("Guruhlarni o‘qib bo‘lmadi: {}".format(exc), "error")
    return redirect(url_for("cabinet.profile_detail", profile_id=profile_id))


@bp.route("/profil/<int:profile_id>/guruh/<int:group_id>", methods=["POST"])
@login_required
def group_toggle(profile_id, group_id):
    own_profile_or_404(profile_id)
    grp = query(
        "SELECT * FROM groups WHERE id = ? AND profile_id = ?",
        (group_id, profile_id),
        one=True,
    )
    if grp:
        new_state = 0 if grp["enabled"] else 1
        execute(
            "UPDATE groups SET enabled = ?, status = CASE WHEN ? = 1 THEN 'ok' "
            "ELSE status END WHERE id = ?",
            (new_state, new_state, group_id),
        )
        count = scalar(
            "SELECT COUNT(*) FROM groups WHERE profile_id = ? AND enabled = 1",
            (profile_id,),
        )
        update("profiles", {"groups_count": count}, "id = ?", (profile_id,))
    return redirect(url_for("cabinet.profile_detail", profile_id=profile_id) + "#guruhlar")


@bp.route("/profil/<int:profile_id>/guruhlar/ommaviy", methods=["POST"])
@login_required
def groups_bulk(profile_id):
    own_profile_or_404(profile_id)
    action = request.form.get("action")

    if action == "enable_all":
        execute(
            "UPDATE groups SET enabled = 1, status = 'ok' WHERE profile_id = ? "
            "AND status NOT IN ('banned','removed')",
            (profile_id,),
        )
        flash("Barcha guruhlar yoqildi", "success")
    elif action == "disable_all":
        execute("UPDATE groups SET enabled = 0 WHERE profile_id = ?", (profile_id,))
        flash("Barcha guruhlar o‘chirildi", "info")
    elif action == "clean":
        removed = execute(
            "DELETE FROM groups WHERE profile_id = ? AND status IN "
            "('banned','removed','invalid')",
            (profile_id,),
        )
        flash("Ishlamaydigan guruhlar tozalandi", "success")

    count = scalar(
        "SELECT COUNT(*) FROM groups WHERE profile_id = ? AND enabled = 1", (profile_id,)
    )
    update("profiles", {"groups_count": count}, "id = ?", (profile_id,))
    return redirect(url_for("cabinet.profile_detail", profile_id=profile_id) + "#guruhlar")


@bp.route("/profil/<int:profile_id>/ochirish", methods=["POST"])
@login_required
def profile_delete(profile_id):
    profile = own_profile_or_404(profile_id)
    worker.stop_profile(profile_id, "O‘chirilmoqda")
    try:
        tg.logout_session(profile["session_string"])
    except Exception:
        pass
    execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
    audit(current_user()["id"], "profile_delete", profile_id)
    flash("Profil o‘chirildi", "info")
    return redirect(url_for("cabinet.profiles"))


# ==================================================================== xabarlar
@bp.route("/xabarlar", methods=["GET", "POST"])
@login_required
def ads():
    user = current_user()

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()[:80]
        body = sanitize_ad_html((request.form.get("body") or "").strip())

        if not body:
            flash("Xabar matnini kiriting", "error")
            return redirect(url_for("cabinet.ads"))
        if len(body) > 4000:
            flash("Xabar matni 4000 belgidan oshmasligi kerak", "error")
            return redirect(url_for("cabinet.ads"))

        media_path, media_type = _save_media(request.files.get("media"))

        ad_id = execute(
            "INSERT INTO ads(user_id, title, body, parse_mode, media_path, media_type, "
            "is_active, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                user["id"],
                title or "Xabar",
                body,
                "html",
                media_path,
                media_type,
                1,
                now_str(),
                now_str(),
            ),
        )
        audit(user["id"], "ad_create", ad_id)
        flash("Xabar yaratildi", "success")
        return redirect(url_for("cabinet.ads"))

    rows = query(
        "SELECT a.*, (SELECT COUNT(*) FROM profiles p WHERE p.active_ad_id = a.id) "
        "AS used_by FROM ads a WHERE a.user_id = ? ORDER BY a.id DESC",
        (user["id"],),
    )
    return render_template("cabinet/ads.html", ads=rows)


@bp.route("/xabar/<int:ad_id>", methods=["GET", "POST"])
@login_required
def ad_edit(ad_id):
    ad = own_ad_or_404(ad_id)

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()[:80]
        body = sanitize_ad_html((request.form.get("body") or "").strip())
        if not body:
            flash("Xabar matnini kiriting", "error")
            return redirect(url_for("cabinet.ad_edit", ad_id=ad_id))

        data = {
            "title": title or "Xabar",
            "body": body,
            "is_active": 1 if request.form.get("is_active") else 0,
            "updated_at": now_str(),
        }

        if request.form.get("remove_media"):
            _delete_media(ad["media_path"])
            data["media_path"] = ""
            data["media_type"] = ""
        else:
            media_path, media_type = _save_media(request.files.get("media"))
            if media_path:
                _delete_media(ad["media_path"])
                data["media_path"] = media_path
                data["media_type"] = media_type

        update("ads", data, "id = ?", (ad_id,))
        flash("Xabar saqlandi", "success")
        return redirect(url_for("cabinet.ads"))

    used_by = query(
        "SELECT id, title, phone FROM profiles WHERE active_ad_id = ?", (ad_id,)
    )
    return render_template("cabinet/ad_edit.html", ad=ad, used_by=used_by)


@bp.route("/xabar/<int:ad_id>/ochirish", methods=["POST"])
@login_required
def ad_delete(ad_id):
    ad = own_ad_or_404(ad_id)
    execute(
        "UPDATE profiles SET active_ad_id = NULL, status = CASE WHEN status = 'running' "
        "THEN 'paused' ELSE status END WHERE active_ad_id = ?",
        (ad_id,),
    )
    _delete_media(ad["media_path"])
    execute("DELETE FROM ads WHERE id = ?", (ad_id,))
    flash("Xabar o‘chirildi", "info")
    return redirect(url_for("cabinet.ads"))


def _save_media(file_storage):
    """Rasmni saqlaydi. Qaytaradi: (nisbiy yo'l, tur)."""
    if not file_storage or not file_storage.filename:
        return "", ""
    ext = os.path.splitext(secure_filename(file_storage.filename))[1].lower()
    if ext not in ALLOWED_IMAGES:
        flash("Faqat rasm fayllari qabul qilinadi (jpg, png, webp, gif)", "warning")
        return "", ""
    name = "{}{}".format(uuid.uuid4().hex, ext)
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    file_storage.save(os.path.join(config.UPLOAD_DIR, name))
    return "static/uploads/{}".format(name), "photo"


def _delete_media(rel_path):
    if not rel_path:
        return
    full = os.path.join(config.BASE_DIR, rel_path.replace("/", os.sep))
    try:
        if os.path.exists(full):
            os.remove(full)
    except OSError:
        pass


# ==================================================================== statistika
@bp.route("/statistika")
@login_required
def stats():
    uid = current_user()["id"]
    days = safe_int(request.args.get("days"), 30, 7, 90)

    frm = (now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    rows = query(
        "SELECT day, SUM(sent) AS sent, SUM(failed) AS failed FROM stats_daily "
        "WHERE user_id = ? AND day >= ? GROUP BY day",
        (uid, frm),
    )
    by_day = {r["day"]: r for r in rows}
    chart, total_sent, total_failed = [], 0, 0
    for i in range(days):
        day = (now() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        row = by_day.get(day)
        sent = row["sent"] if row else 0
        failed = row["failed"] if row else 0
        total_sent += sent
        total_failed += failed
        chart.append({"label": day[8:10] + "." + day[5:7], "value": sent})

    per_profile = query(
        "SELECT p.id, p.title, p.phone, p.sent_total, p.sent_24h, p.failed_total, "
        "p.groups_count, p.status FROM profiles p WHERE p.user_id = ? "
        "ORDER BY p.sent_total DESC",
        (uid,),
    )

    top_groups = query(
        "SELECT g.title, g.members, g.sent_count, p.title AS ptitle FROM groups g "
        "JOIN profiles p ON p.id = g.profile_id WHERE p.user_id = ? "
        "ORDER BY g.sent_count DESC LIMIT 15",
        (uid,),
    )

    attempts = total_sent + total_failed
    return render_template(
        "cabinet/stats.html",
        chart=chart,
        days=days,
        total_sent=total_sent,
        total_failed=total_failed,
        success_rate=round(total_sent / attempts * 100, 1) if attempts else 100.0,
        per_profile=per_profile,
        top_groups=top_groups,
    )


# ==================================================================== to'lovlar
@bp.route("/tolovlar")
@login_required
def billing():
    user = current_user()
    uid = user["id"]

    profiles = query(
        "SELECT p.*, s.id AS sub_id, s.status AS sub_status, s.auto_renew AS sub_auto, "
        "s.next_charge_at, s.price AS sub_price FROM profiles p "
        "LEFT JOIN subscriptions s ON s.profile_id = p.id "
        "WHERE p.user_id = ? ORDER BY p.id DESC",
        (uid,),
    )
    cards = query(
        "SELECT * FROM cards WHERE user_id = ? AND status = 'active' ORDER BY id DESC",
        (uid,),
    )
    payments = query(
        "SELECT pm.*, p.title AS ptitle FROM payments pm "
        "LEFT JOIN profiles p ON p.id = pm.profile_id "
        "WHERE pm.user_id = ? ORDER BY pm.id DESC LIMIT 40",
        (uid,),
    )

    monthly = billing_svc.price() * max(
        sum(1 for p in profiles if p["auto_renew"] and p["plan"] == "pro"), 0
    )

    return render_template(
        "cabinet/billing.html",
        profiles=profiles,
        cards=cards,
        payments=payments,
        price=billing_svc.price(),
        monthly=monthly,
        card_pending=session.get("card_pending"),
        payme_ready=bool(config.PAYME_MERCHANT_ID),
        subscribe_ready=subscribe_api.configured,
    )


@bp.route("/tolov/yaratish", methods=["POST"])
@login_required
def payment_create():
    """Payme checkout orqali bir martalik to'lov."""
    user = current_user()
    profile_id = safe_int(request.form.get("profile_id"), 0)
    profile = own_profile_or_404(profile_id) if profile_id else None
    if not profile:
        flash("Profil tanlanmadi", "error")
        return redirect(url_for("cabinet.billing"))

    amount = billing_svc.price()
    payment_id = billing_svc.create_payment(
        user["id"],
        amount,
        profile_id=profile_id,
        description="AutoXabar PRO — {}".format(profile["title"] or profile["phone"]),
    )

    if not config.PAYME_MERCHANT_ID:
        flash("To‘lov tizimi hali sozlanmagan. Administratorga murojaat qiling", "error")
        return redirect(url_for("cabinet.billing"))

    back = url_for("payme.result", payment_id=payment_id, _external=True)
    url = checkout_url(payment_id, amount, callback_url=back)
    return redirect(url)


@bp.route("/tolov/balansdan", methods=["POST"])
@login_required
def pay_from_balance():
    user = current_user()
    profile_id = safe_int(request.form.get("profile_id"), 0)
    own_profile_or_404(profile_id)
    ok, message = billing_svc.pay_from_balance(user["id"], profile_id)
    flash(message, "success" if ok else "error")
    return redirect(url_for("cabinet.billing"))


@bp.route("/avto-tolov", methods=["POST"])
@login_required
def auto_renew_toggle():
    profile_id = safe_int(request.form.get("profile_id"), 0)
    own_profile_or_404(profile_id)
    on = request.form.get("on") == "1"

    if on and not billing_svc.default_card(current_user()["id"]):
        flash("Avval kartani qo‘shing va tasdiqlang", "warning")
        return redirect(url_for("cabinet.billing"))

    billing_svc.cancel_auto_renew(profile_id, on)
    flash("Avto-to‘lov {}".format("yoqildi" if on else "o‘chirildi"),
          "success" if on else "info")
    return redirect(url_for("cabinet.billing"))


# ---------------------------------------------------------------- kartalar
@bp.route("/karta/qoshish", methods=["POST"])
@login_required
def card_add():
    """Payme Subscribe: karta tokenini yaratib, SMS kod so'raladi."""
    user = current_user()

    if not subscribe_api.configured:
        flash("Avto-to‘lov tizimi sozlanmagan. Administratorga murojaat qiling", "error")
        return redirect(url_for("cabinet.billing"))

    number = (request.form.get("number") or "").replace(" ", "")
    expire = (request.form.get("expire") or "").replace("/", "").replace(" ", "")

    if len(number) != 16 or not number.isdigit():
        flash("Karta raqamini to‘liq kiriting", "error")
        return redirect(url_for("cabinet.billing"))
    if len(expire) != 4 or not expire.isdigit():
        flash("Amal qilish muddatini OO/YY ko‘rinishida kiriting", "error")
        return redirect(url_for("cabinet.billing"))

    # Payme MMYY emas, YYMM formatini kutadi
    expire_payme = expire[2:] + expire[:2]

    result = subscribe_api.cards_create(number, expire_payme)
    if "error" in result:
        from services.payme import _msg

        flash("Karta qo‘shilmadi: {}".format(_msg(result["error"])), "error")
        return redirect(url_for("cabinet.billing"))

    card = (result.get("result") or {}).get("card") or {}
    token = card.get("token", "")
    if not token:
        flash("Karta tokeni olinmadi", "error")
        return redirect(url_for("cabinet.billing"))

    sent = subscribe_api.cards_get_verify_code(token)
    if "error" in sent:
        from services.payme import _msg

        flash("SMS kod yuborilmadi: {}".format(_msg(sent["error"])), "error")
        return redirect(url_for("cabinet.billing"))

    session["card_pending"] = {
        "token": token,
        "masked": card.get("number", "") or ("**** " + number[-4:]),
        "expire": expire,
        "phone": (sent.get("result") or {}).get("phone", ""),
    }
    flash("Kartaga bog‘langan raqamga SMS kod yuborildi", "success")
    return redirect(url_for("cabinet.billing") + "#kartalar")


@bp.route("/karta/tasdiqlash", methods=["POST"])
@login_required
def card_verify():
    user = current_user()
    pending = session.get("card_pending")
    if not pending:
        flash("Sessiya muddati tugadi. Qaytadan boshlang", "error")
        return redirect(url_for("cabinet.billing"))

    code = "".join(request.form.getlist("code")).strip()
    if not code:
        flash("SMS kodni kiriting", "error")
        return redirect(url_for("cabinet.billing") + "#kartalar")
    result = subscribe_api.cards_verify(pending["token"], code)
    if "error" in result:
        from services.payme import _msg

        flash("Tasdiqlanmadi: {}".format(_msg(result["error"])), "error")
        return redirect(url_for("cabinet.billing") + "#kartalar")

    card = (result.get("result") or {}).get("card") or {}
    has_card = scalar("SELECT COUNT(*) FROM cards WHERE user_id = ? AND status = 'active'",
                      (user["id"],))

    card_id = execute(
        "INSERT INTO cards(user_id, token, number_masked, expire, verified, is_default, "
        "recurrent, status, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (
            user["id"],
            card.get("token") or pending["token"],
            card.get("number") or pending["masked"],
            pending["expire"],
            1,
            0 if has_card else 1,
            1,
            "active",
            now_str(),
        ),
    )
    session.pop("card_pending", None)
    audit(user["id"], "card_add", card_id)
    flash("Karta muvaffaqiyatli qo‘shildi. Endi avto-to‘lovni yoqishingiz mumkin",
          "success")
    return redirect(url_for("cabinet.billing") + "#kartalar")


@bp.route("/karta/bekor", methods=["POST"])
@login_required
def card_cancel():
    session.pop("card_pending", None)
    return redirect(url_for("cabinet.billing") + "#kartalar")


@bp.route("/karta/<int:card_id>/ochirish", methods=["POST"])
@login_required
def card_delete(card_id):
    user = current_user()
    card = query(
        "SELECT * FROM cards WHERE id = ? AND user_id = ?", (card_id, user["id"]), one=True
    )
    if not card:
        flash("Karta topilmadi", "error")
        return redirect(url_for("cabinet.billing"))

    try:
        subscribe_api.cards_remove(card["token"])
    except Exception:
        pass

    execute("UPDATE cards SET status = 'removed' WHERE id = ?", (card_id,))
    execute(
        "UPDATE subscriptions SET auto_renew = 0 WHERE card_id = ? AND user_id = ?",
        (card_id, user["id"]),
    )
    remaining = query(
        "SELECT id FROM cards WHERE user_id = ? AND status = 'active' LIMIT 1",
        (user["id"],),
        one=True,
    )
    if remaining:
        execute("UPDATE cards SET is_default = 1 WHERE id = ?", (remaining["id"],))
    else:
        execute(
            "UPDATE profiles SET auto_renew = 0 WHERE user_id = ?", (user["id"],)
        )

    flash("Karta o‘chirildi", "info")
    return redirect(url_for("cabinet.billing") + "#kartalar")


@bp.route("/karta/<int:card_id>/asosiy", methods=["POST"])
@login_required
def card_default(card_id):
    user = current_user()
    execute("UPDATE cards SET is_default = 0 WHERE user_id = ?", (user["id"],))
    execute(
        "UPDATE cards SET is_default = 1 WHERE id = ? AND user_id = ?",
        (card_id, user["id"]),
    )
    flash("Asosiy karta o‘zgartirildi", "success")
    return redirect(url_for("cabinet.billing") + "#kartalar")


# ==================================================================== bildirishnoma
@bp.route("/bildirishnomalar")
@login_required
def notifications():
    uid = current_user()["id"]
    rows = query(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 100", (uid,)
    )
    return render_template("cabinet/notifications.html", items=rows)


@bp.route("/bildirishnomalar/oqilgan", methods=["POST"])
@login_required
def notifications_read():
    execute(
        "UPDATE notifications SET is_read = 1 WHERE user_id = ?", (current_user()["id"],)
    )
    return redirect(request.referrer or url_for("cabinet.notifications"))


# ==================================================================== sozlamalar
@bp.route("/sozlamalar", methods=["GET", "POST"])
@login_required
def settings():
    user = current_user()

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()[:60]
        email = (request.form.get("email") or "").strip()[:120]
        telegram_id = (request.form.get("telegram_id") or "").strip()[:32]
        update(
            "users",
            {
                "name": name,
                "email": email,
                "telegram_id": telegram_id,
                "updated_at": now_str(),
            },
            "id = ?",
            (user["id"],),
        )
        flash("Ma'lumotlar saqlandi", "success")
        return redirect(url_for("cabinet.settings"))

    referrals = scalar(
        "SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user["id"],)
    )
    return render_template("cabinet/settings.html", referrals=referrals)
