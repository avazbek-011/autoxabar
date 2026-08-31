"""Fon vazifalari rejalashtiruvchisi (APScheduler)."""
import atexit
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from services import billing, worker
from services import telegram_engine as tg

log = logging.getLogger("scheduler")

_scheduler = None


def _safe(func, name):
    def wrapper():
        try:
            func()
        except Exception:
            log.exception("Fon vazifasi xatosi: %s", name)

    wrapper.__name__ = name
    return wrapper


def _charge_due():
    ok, fail = billing.charge_due_subscriptions()
    if ok or fail:
        log.info("Avto-to'lov: %s muvaffaqiyatli, %s xato", ok, fail)


def _expire():
    count = billing.expire_overdue()
    if count:
        log.info("Muddati tugagan obunalar: %s", count)
    billing.notify_expiring()


def start(app=None):
    """Rejalashtiruvchini ishga tushiradi (bir marta)."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    sched = BackgroundScheduler(
        timezone="Asia/Tashkent",
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 120},
    )

    # Yuborish sikllarini tekshirish — har 30 soniyada
    sched.add_job(_safe(worker.tick, "worker_tick"), "interval", seconds=30, id="tick")

    # Hisoblagichlarni yangilash — har 5 daqiqada
    sched.add_job(
        _safe(worker.refresh_counters, "counters"), "interval", minutes=5, id="counters"
    )

    # Avto-to'lovlar — har 30 daqiqada
    sched.add_job(_safe(_charge_due, "charge"), "interval", minutes=30, id="charge")

    # Muddati tugaganlar — soatiga bir marta
    sched.add_job(_safe(_expire, "expire"), "interval", minutes=60, id="expire")

    # Bo'sh turgan Telegram ulanishlarini yopish — har 5 daqiqada
    sched.add_job(
        _safe(tg.close_idle_clients, "tg_gc"), "interval", minutes=5, id="tg_gc"
    )

    # Jurnal tozalash — kuniga bir marta (03:30)
    sched.add_job(
        _safe(worker.cleanup_logs, "cleanup"), "cron", hour=3, minute=30, id="cleanup"
    )

    sched.start()
    _scheduler = sched
    atexit.register(shutdown)
    log.info("Rejalashtiruvchi ishga tushdi")
    return sched


def shutdown():
    global _scheduler
    if _scheduler:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
        _scheduler = None
    worker.stop_all()


def jobs():
    if not _scheduler:
        return []
    return [
        {
            "id": job.id,
            "next": job.next_run_time.strftime("%d.%m.%Y %H:%M:%S")
            if job.next_run_time
            else "—",
        }
        for job in _scheduler.get_jobs()
    ]


def is_running():
    return _scheduler is not None and _scheduler.running
