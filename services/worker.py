"""Avto-yuborish ishchisi.

Har bir "running" profil uchun sikl:
    interval kutish -> barcha yoqilgan guruhlarga xabar yuborish -> statistika
Aqlli dam olish: 1 soat uzluksiz ishlagach 3-5 daqiqa tanaffus (ban profilaktikasi).
"""
import logging
import random
import threading
import time
from datetime import timedelta

from core.db import execute, now, now_str, query, update, worker_db
from core.utils import dt_str, notify, parse_dt
from services import telegram_engine as tg

log = logging.getLogger("worker")

# Guruhlar orasidagi tasodifiy pauza (soniya) — flood oldini oladi
GAP_MIN, GAP_MAX = 3.0, 8.0

# Aqlli dam olish
WORK_BLOCK_MIN = 60          # uzluksiz ishlash (daqiqa)
REST_MIN, REST_MAX = 3, 5    # tanaffus (daqiqa)

# Bir siklda ko'pi bilan shuncha guruh
MAX_GROUPS_PER_CYCLE = 400

FREE_FOOTER = (
    "\n\n➖➖➖➖➖➖➖➖\n"
    "📢 Xabaringiz avtomatik tarqatilsin — @AutoXabarbot | vipadsuz.uz"
)

_stop = threading.Event()
_thread = None
_running_now = set()
_lock = threading.Lock()


# ---------------------------------------------------------------- yordamchi
def _log_send(db, profile_id, group, ad_id, status, error=""):
    execute(
        "INSERT INTO send_log(profile_id, group_id, ad_id, chat_title, status, error, "
        "created_at) VALUES(?,?,?,?,?,?,?)",
        (
            profile_id,
            group["id"] if group else None,
            ad_id,
            group["title"] if group else "",
            status,
            error[:250],
            now_str(),
        ),
        db=db,
    )


def _bump_daily(db, user_id, profile_id, sent, failed):
    day = now().strftime("%Y-%m-%d")
    execute(
        "INSERT INTO stats_daily(day, user_id, profile_id, sent, failed) VALUES(?,?,?,?,?) "
        "ON CONFLICT(day, user_id, profile_id) DO UPDATE SET "
        "sent = sent + excluded.sent, failed = failed + excluded.failed",
        (day, user_id, profile_id, sent, failed),
        db=db,
    )


def _pause(db, profile, status, note, notify_user=True):
    update(
        "profiles",
        {"status": status, "status_note": note[:250], "updated_at": now_str()},
        "id = ?",
        (profile["id"],),
        db=db,
    )
    if notify_user:
        notify(
            profile["user_id"],
            "Profil to'xtatildi",
            "«{}»: {}".format(profile["title"] or profile["phone"], note),
            "danger",
            "/kabinet/profillar",
        )


def compose_text(ad, profile):
    """Xabar matni: FREE rejimda pastiga reklama qo'shiladi."""
    body = ad["body"] or ""
    if profile["plan"] != "pro":
        body += FREE_FOOTER
    return body


# ---------------------------------------------------------------- bitta sikl
def run_profile_cycle(profile_id):
    """Bitta profil uchun to'liq yuborish siklini bajaradi."""
    with _lock:
        if profile_id in _running_now:
            return 0, 0
        _running_now.add(profile_id)

    sent = failed = 0
    try:
        with worker_db() as db:
            profile = query(
                "SELECT * FROM profiles WHERE id = ?", (profile_id,), one=True, db=db
            )
            if not profile or profile["status"] != "running":
                return 0, 0

            ad = None
            if profile["active_ad_id"]:
                ad = query(
                    "SELECT * FROM ads WHERE id = ? AND is_active = 1",
                    (profile["active_ad_id"],),
                    one=True,
                    db=db,
                )
            if not ad:
                _pause(db, profile, "paused", "Faol xabar tanlanmagan")
                return 0, 0

            groups = query(
                "SELECT * FROM groups WHERE profile_id = ? AND enabled = 1 "
                "AND status IN ('ok','slow') ORDER BY last_sent_at IS NULL DESC, "
                "last_sent_at ASC LIMIT ?",
                (profile_id, MAX_GROUPS_PER_CYCLE),
                db=db,
            )
            if not groups:
                update(
                    "profiles",
                    {
                        "status_note": "Yoqilgan guruh yo'q",
                        "next_run_at": dt_str(now() + timedelta(minutes=profile["interval_min"])),
                        "updated_at": now_str(),
                    },
                    "id = ?",
                    (profile_id,),
                    db=db,
                )
                return 0, 0

            text = compose_text(ad, profile)
            media = ad["media_path"] if profile["plan"] == "pro" else ""
            if media:
                import os

                from config import config

                media = os.path.join(config.BASE_DIR, media.lstrip("/\\"))
                if not os.path.exists(media):
                    media = ""

            stop_reason = None
            for group in groups:
                if _stop.is_set():
                    break

                result = tg.send_message(
                    profile["session_string"],
                    group["chat_id"],
                    text,
                    parse_mode=ad["parse_mode"],
                    media_path=media or None,
                )

                if result.ok:
                    sent += 1
                    execute(
                        "UPDATE groups SET sent_count = sent_count + 1, last_sent_at = ?, "
                        "status = 'ok', status_note = '' WHERE id = ?",
                        (now_str(), group["id"]),
                        db=db,
                    )
                    _log_send(db, profile_id, group, ad["id"], "ok")
                else:
                    failed += 1
                    _log_send(db, profile_id, group, ad["id"], "fail", result.error)

                    if result.code in ("muted", "banned", "removed", "invalid"):
                        execute(
                            "UPDATE groups SET fail_count = fail_count + 1, enabled = 0, "
                            "status = ?, status_note = ? WHERE id = ?",
                            (result.code, result.error[:250], group["id"]),
                            db=db,
                        )
                    elif result.code == "slowmode":
                        execute(
                            "UPDATE groups SET fail_count = fail_count + 1, status = 'slow', "
                            "slowmode_sec = ?, status_note = ? WHERE id = ?",
                            (result.wait, result.error[:250], group["id"]),
                            db=db,
                        )
                    else:
                        execute(
                            "UPDATE groups SET fail_count = fail_count + 1 WHERE id = ?",
                            (group["id"],),
                            db=db,
                        )

                    if result.code == "account_banned":
                        stop_reason = ("banned", "Telegram akkaunt bloklangan")
                        break
                    if result.code == "invalid" and "Sessiya" in result.error:
                        stop_reason = ("error", "Sessiya bekor qilingan — qayta ulang")
                        break
                    if result.code == "flood":
                        wait = max(int(result.wait or 0), 60)
                        update(
                            "profiles",
                            {
                                "rest_until": dt_str(now() + timedelta(seconds=wait)),
                                "status_note": "FloodWait: {} soniya kutilmoqda".format(wait),
                                "updated_at": now_str(),
                            },
                            "id = ?",
                            (profile_id,),
                            db=db,
                        )
                        break

                time.sleep(random.uniform(GAP_MIN, GAP_MAX))

            # --- Sikl yakuni ---
            fresh = query(
                "SELECT * FROM profiles WHERE id = ?", (profile_id,), one=True, db=db
            )
            if stop_reason:
                _pause(db, fresh, stop_reason[0], stop_reason[1])
            else:
                data = {
                    "sent_total": fresh["sent_total"] + sent,
                    "failed_total": fresh["failed_total"] + failed,
                    "last_run_at": now_str(),
                    "next_run_at": dt_str(now() + timedelta(minutes=fresh["interval_min"])),
                    "updated_at": now_str(),
                }
                # Aqlli dam olish
                if fresh["smart_rest"]:
                    started = parse_dt(fresh["cycle_started_at"])
                    if not started:
                        data["cycle_started_at"] = now_str()
                    elif (now() - started) >= timedelta(minutes=WORK_BLOCK_MIN):
                        rest = random.randint(REST_MIN, REST_MAX)
                        data["rest_until"] = dt_str(now() + timedelta(minutes=rest))
                        data["cycle_started_at"] = dt_str(now() + timedelta(minutes=rest))
                        data["status_note"] = "Aqlli dam olish: {} daqiqa".format(rest)
                update("profiles", data, "id = ?", (profile_id,), db=db)

            execute(
                "UPDATE ads SET sent_count = sent_count + ? WHERE id = ?",
                (sent, ad["id"]),
                db=db,
            )
            _bump_daily(db, profile["user_id"], profile_id, sent, failed)

    except Exception:
        log.exception("Profil sikli xatosi (%s)", profile_id)
    finally:
        with _lock:
            _running_now.discard(profile_id)

    return sent, failed


# ---------------------------------------------------------------- tik
def tick():
    """Har bir chaqiruvda muddati kelgan profillarni ishga tushiradi."""
    try:
        with worker_db() as db:
            rows = query(
                "SELECT id FROM profiles WHERE status = 'running' "
                "AND (next_run_at IS NULL OR next_run_at <= ?) "
                "AND (rest_until IS NULL OR rest_until <= ?)",
                (now_str(), now_str()),
                db=db,
            )
            ids = [r["id"] for r in rows]
    except Exception:
        log.exception("tick: profillarni o'qishda xato")
        return 0

    started = 0
    for pid in ids:
        with _lock:
            if pid in _running_now:
                continue
        threading.Thread(
            target=run_profile_cycle, args=(pid,), name="cycle-%s" % pid, daemon=True
        ).start()
        started += 1
    return started


def refresh_counters():
    """sent_24h va groups_count maydonlarini yangilaydi."""
    since = dt_str(now() - timedelta(hours=24))
    with worker_db() as db:
        execute(
            "UPDATE profiles SET sent_24h = (SELECT COUNT(*) FROM send_log s "
            "WHERE s.profile_id = profiles.id AND s.status = 'ok' AND s.created_at > ?)",
            (since,),
            db=db,
        )
        execute(
            "UPDATE profiles SET groups_count = (SELECT COUNT(*) FROM groups g "
            "WHERE g.profile_id = profiles.id AND g.enabled = 1)",
            db=db,
        )


def cleanup_logs(keep_days=14):
    """Eski jurnal yozuvlarini o'chiradi."""
    limit = dt_str(now() - timedelta(days=keep_days))
    with worker_db() as db:
        execute("DELETE FROM send_log WHERE created_at < ?", (limit,), db=db)
        execute(
            "DELETE FROM login_attempts WHERE created_at < ?",
            (dt_str(now() - timedelta(days=3)),),
            db=db,
        )


# ---------------------------------------------------------------- boshqaruv
def start_profile(profile_id, db=None):
    """Profilni ishga tushiradi. (ok, xabar)"""
    profile = query("SELECT * FROM profiles WHERE id = ?", (profile_id,), one=True, db=db)
    if not profile:
        return False, "Profil topilmadi"
    if profile["status"] in ("banned",):
        return False, "Akkaunt bloklangan"
    if not profile["session_string"]:
        return False, "Avval Telegram akkauntini ulang"
    if not profile["active_ad_id"]:
        return False, "Faol xabarni tanlang"

    expires = parse_dt(profile["expires_at"])
    if profile["plan"] == "pro" and (not expires or expires <= now()):
        return False, "Obuna muddati tugagan"

    enabled = query(
        "SELECT COUNT(*) AS c FROM groups WHERE profile_id = ? AND enabled = 1",
        (profile_id,),
        one=True,
        db=db,
    )
    if not enabled or enabled["c"] == 0:
        return False, "Kamida bitta guruhni yoqing"

    update(
        "profiles",
        {
            "status": "running",
            "status_note": "",
            "next_run_at": now_str(),
            "cycle_started_at": now_str(),
            "rest_until": None,
            "updated_at": now_str(),
        },
        "id = ?",
        (profile_id,),
        db=db,
    )
    return True, "Profil ishga tushdi"


def stop_profile(profile_id, note="Foydalanuvchi to'xtatdi", db=None):
    update(
        "profiles",
        {
            "status": "paused",
            "status_note": note,
            "next_run_at": None,
            "rest_until": None,
            "updated_at": now_str(),
        },
        "id = ?",
        (profile_id,),
        db=db,
    )
    return True, "Profil to'xtatildi"


def is_alive():
    return _thread is not None and _thread.is_alive()


def stop_all():
    _stop.set()
