"""AutoXabar / VIPADSUZ — Flask ilovasi."""
import logging
import os
import sys

from flask import Flask, g, redirect, render_template, request, url_for

from config import config
from core import db as dbmod
from core.auth import current_user
from core.db import get_setting, init_db, now, query
from core.utils import (
    compact,
    csrf_token,
    csrf_valid,
    date_fmt,
    dt_fmt,
    money,
    num,
    pretty_phone,
    time_ago,
    time_left,
    truncate,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)-12s %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)
log = logging.getLogger("app")

ASSET_VERSION = "1.0.0"

# CSRF tekshiruvidan ozod yo'llar (tashqi xizmatlar chaqiradi)
CSRF_EXEMPT = {"payme.merchant_endpoint"}


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(config)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["PERMANENT_SESSION_LIFETIME"] = config.PERMANENT_SESSION_LIFETIME
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
    app.config["TEMPLATES_AUTO_RELOAD"] = config.DEBUG
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    os.makedirs(config.SESSION_DIR, exist_ok=True)
    init_db()

    _register_filters(app)
    _register_context(app)
    _register_hooks(app)
    _register_blueprints(app)
    _register_errors(app)
    _start_scheduler(app)

    return app


def _start_scheduler(app):
    """Fon vazifalarini yoqadi.

    create_app() ichida turgani uchun gunicorn/waitress kabi WSGI serverlar
    ostida ham ishlaydi. Dev-reloader ikki marta ishga tushirmasligi uchun
    faqat asosiy jarayonda yoqiladi.
    """
    if not config.RUN_SCHEDULER:
        return
    if config.DEBUG and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return  # reloaderning ota-jarayoni

    from services import scheduler

    scheduler.start(app)


# ------------------------------------------------------------------ filtrlar
def _register_filters(app):
    app.jinja_env.filters["money"] = money
    app.jinja_env.filters["num"] = num
    app.jinja_env.filters["compact"] = compact
    app.jinja_env.filters["phone"] = pretty_phone
    app.jinja_env.filters["ago"] = time_ago
    app.jinja_env.filters["dt"] = dt_fmt
    app.jinja_env.filters["date"] = date_fmt
    app.jinja_env.filters["left"] = time_left
    app.jinja_env.filters["short"] = truncate


# ------------------------------------------------------------------ kontekst
def _register_context(app):
    from services import billing

    @app.context_processor
    def inject():
        user = current_user()
        ctx = {
            "cfg": config,
            "contacts": {
                "channel": get_setting("support_channel", "") or config.TELEGRAM_CHANNEL,
                "bot": get_setting("support_bot", "") or config.TELEGRAM_BOT,
                "person": get_setting("support_contact", "") or config.SUPPORT_CONTACT,
            },
            "user": user,
            "year": now().year,
            "asset_v": ASSET_VERSION,
            "csrf_token": csrf_token,
            "price": billing.price(),
            "unread_count": 0,
            "recent_notifications": [],
            "nav_counts": None,
            "plan_box": None,
            "stats_admin": None,
        }
        if not user:
            return ctx

        ctx["unread_count"] = query(
            "SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND is_read = 0",
            (user["id"],),
            one=True,
        )["c"]
        ctx["recent_notifications"] = query(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 6",
            (user["id"],),
        )
        ctx["nav_counts"] = {
            "profiles": query(
                "SELECT COUNT(*) AS c FROM profiles WHERE user_id = ?",
                (user["id"],),
                one=True,
            )["c"],
            "ads": query(
                "SELECT COUNT(*) AS c FROM ads WHERE user_id = ?", (user["id"],), one=True
            )["c"],
        }

        # Yon paneldagi obuna qutisi
        active = query(
            "SELECT COUNT(*) AS c FROM profiles WHERE user_id = ? AND plan = 'pro' "
            "AND expires_at > ?",
            (user["id"], dbmod.now_str()),
            one=True,
        )["c"]
        total = ctx["nav_counts"]["profiles"]
        if total == 0:
            ctx["plan_box"] = {
                "title": "Boshlash",
                "value": "Profil qo‘shing",
                "action": "Narxlarni ko‘rish",
            }
        elif active == 0:
            ctx["plan_box"] = {
                "title": "Obuna kerak",
                "value": "{} so‘m / oy".format(num(billing.price())),
                "action": "Obunani yoqish",
            }
        else:
            ctx["plan_box"] = {
                "title": "PRO faol",
                "value": "{} / {} profil".format(active, total),
                "action": "Boshqarish",
            }

        if user["role"] == "admin" and request.blueprint == "admin":
            ctx["stats_admin"] = {
                "users": query("SELECT COUNT(*) AS c FROM users", one=True)["c"],
                "profiles": query("SELECT COUNT(*) AS c FROM profiles", one=True)["c"],
            }
        return ctx


# ------------------------------------------------------------------ hooklar
def _register_hooks(app):
    @app.before_request
    def guard():
        # CSRF: barcha o'zgartiruvchi so'rovlar uchun
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if request.endpoint not in CSRF_EXEMPT and not csrf_valid():
                log.warning("CSRF xato: %s %s", request.method, request.path)
                return render_template("errors/csrf.html"), 400

    @app.teardown_appcontext
    def close(exc):
        dbmod.close_db(exc)

    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.path.startswith("/static/"):
            resp.headers.setdefault("Cache-Control", "public, max-age=604800")
        return resp


# ------------------------------------------------------------------ marshrutlar
def _register_blueprints(app):
    from blueprints.admin import bp as admin_bp
    from blueprints.auth_bp import bp as auth_bp
    from blueprints.cabinet import bp as cabinet_bp
    from blueprints.payme_bp import bp as payme_bp
    from blueprints.site import bp as site_bp

    app.register_blueprint(site_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cabinet_bp, url_prefix="/kabinet")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(payme_bp)


# ------------------------------------------------------------------ xatoliklar
def _register_errors(app):
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/error.html", code=403,
                               title="Ruxsat yo‘q",
                               text="Bu sahifaga kirish huquqingiz yo‘q."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/error.html", code=404,
                               title="Sahifa topilmadi",
                               text="Siz qidirgan sahifa mavjud emas yoki ko‘chirilgan."), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template("errors/error.html", code=413,
                               title="Fayl juda katta",
                               text="Yuklanayotgan fayl hajmi 16 MB dan oshmasligi kerak."), 413

    @app.errorhandler(500)
    def server_error(e):
        log.exception("Ichki xatolik")
        return render_template("errors/error.html", code=500,
                               title="Ichki xatolik",
                               text="Kutilmagan xatolik yuz berdi. Birozdan so‘ng urinib ko‘ring."), 500


app = create_app()


if __name__ == "__main__":
    from services.telegram_engine import engine_mode

    # Windows konsoli UTF-8 ni qo'llab-quvvatlamasligi mumkin
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    line = "  " + "=" * 54
    print("")
    print(line)
    print("   VIPADSUZ . AutoXabar")
    print(line)
    print("   Manzil     : http://127.0.0.1:{}".format(config.PORT))
    print("   Admin      : {} / {}".format(config.ADMIN_PHONE, config.ADMIN_PASSWORD))
    print("   Narx       : {} so'm / profil / oy".format(config.PRICE_PER_PROFILE))
    print("   Soliq      : {}%".format(config.TAX_PERCENT))
    print("   Telegram   : {} rejim".format(engine_mode().upper()))
    print("   Payme      : {}".format(
        "sozlangan" if config.PAYME_MERCHANT_ID else "sozlanmagan (.env)"))
    print(line)
    print("")

    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, threaded=True)
