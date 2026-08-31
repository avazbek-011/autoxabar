"""Telegram dvigateli (Telethon).

Vazifalari:
  * Telegram akkauntini ulash (telefon -> kod -> 2FA parol)
  * Akkaunt a'zo bo'lgan guruhlarni olish
  * Xabarni guruhlarga belgilangan interval bilan yuborish
  * FloodWait / ban / mute holatlarini aniqlab, avtomatik pauza qilish

Ulanishlar `ClientPool` da saqlanadi: har bir profil uchun bitta doimiy
ulanish ochiladi va sikl davomida qayta ishlatiladi. Har bir xabar uchun
qaytadan ulanish Telegram tomonidan shubhali deb qaraladi va juda sekin.

Telethon yoki API kalitlari mavjud bo'lmasa — DEMO rejimda ishlaydi
(saytning barcha funksiyalari tekshiriladi, faqat haqiqiy yuborish bo'lmaydi).
"""
import asyncio
import hashlib
import logging
import os
import random
import re
import secrets
import threading
import time

from config import config

log = logging.getLogger("tg")

# ---------------------------------------------------------------- Telethon
try:
    from telethon import TelegramClient, errors
    from telethon.sessions import StringSession
    from telethon.tl.types import Channel

    TELETHON_AVAILABLE = True
except ImportError:  # pragma: no cover
    TELETHON_AVAILABLE = False
    TelegramClient = StringSession = errors = Channel = None


_mode_cache = {"value": None, "at": 0.0}


def _forced_mode():
    """Admin sozlamasi ustuvor, bo'lmasa .env dagi qiymat.

    Sozlama har chaqiruvda emas, 10 soniyada bir marta o'qiladi.
    """
    now = time.time()
    if _mode_cache["value"] is not None and now - _mode_cache["at"] < 10:
        return _mode_cache["value"]

    value = ""
    try:
        from core.db import get_setting

        value = (get_setting("telegram_engine", "") or "").strip().lower()
    except Exception:
        value = ""

    if value not in ("auto", "real", "demo"):
        value = (config.TELEGRAM_ENGINE or "auto").lower()

    _mode_cache["value"] = value
    _mode_cache["at"] = now
    return value


def reset_mode_cache():
    _mode_cache["value"] = None


def engine_mode():
    """'real' yoki 'demo'."""
    forced = _forced_mode()
    if forced == "demo":
        return "demo"
    ready = TELETHON_AVAILABLE and config.TELEGRAM_API_ID and config.TELEGRAM_API_HASH
    return "real" if ready else "demo"


def is_demo():
    return engine_mode() == "demo"


def _is_demo_session(session_string):
    return not session_string or session_string.startswith("DEMO:") or is_demo()


# ---------------------------------------------------------------- event loop
class _Loop:
    """Fon oqimida doimiy ishlaydigan asyncio hodisalar sikli."""

    def __init__(self):
        self.loop = None
        self._thread = None
        self._lock = threading.Lock()

    def ensure(self):
        with self._lock:
            if self.loop and self.loop.is_running():
                return self.loop
            self.loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._run, name="tg-loop", daemon=True
            )
            self._thread.start()
            for _ in range(100):
                if self.loop.is_running():
                    break
                time.sleep(0.02)
            return self.loop

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro, timeout=90):
        loop = self.ensure()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)


_loop = _Loop()


def _client_from_session(session_string=""):
    os.makedirs(config.SESSION_DIR, exist_ok=True)
    return TelegramClient(
        StringSession(session_string or None),
        config.TELEGRAM_API_ID,
        config.TELEGRAM_API_HASH,
        device_model="AutoXabar Web",
        system_version="VIPADSUZ 1.0",
        app_version="1.0",
        lang_code="uz",
        system_lang_code="uz",
        connection_retries=3,
        retry_delay=2,
    )


# ---------------------------------------------------------------- ulanish keshi
class ClientPool:
    """Profil sessiyalari uchun doimiy ulanishlar keshi."""

    IDLE_TIMEOUT = 600  # 10 daqiqa ishlatilmasa yopiladi

    def __init__(self):
        self._items = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(session_string):
        return hashlib.sha256(session_string.encode("utf-8")).hexdigest()[:32]

    async def acquire(self, session_string):
        """Ulangan klientni qaytaradi (kerak bo'lsa yaratadi)."""
        key = self._key(session_string)
        with self._lock:
            item = self._items.get(key)

        if item is not None:
            client = item["client"]
            try:
                if not client.is_connected():
                    await client.connect()
                if client.is_connected():
                    item["last"] = time.time()
                    return client
            except Exception:
                log.warning("Keshdagi ulanish tiklanmadi, yangisi ochiladi")
            await self._close(key)

        client = _client_from_session(session_string)
        await client.connect()
        with self._lock:
            self._items[key] = {"client": client, "last": time.time()}
        return client

    async def _close(self, key):
        with self._lock:
            item = self._items.pop(key, None)
        if item:
            try:
                await item["client"].disconnect()
            except Exception:
                pass

    async def drop(self, session_string):
        await self._close(self._key(session_string))

    async def close_idle(self):
        """Uzoq ishlatilmagan ulanishlarni yopadi."""
        now = time.time()
        with self._lock:
            stale = [
                k for k, v in self._items.items()
                if now - v["last"] > self.IDLE_TIMEOUT
            ]
        for key in stale:
            await self._close(key)
        return len(stale)

    async def close_all(self):
        with self._lock:
            keys = list(self._items)
        for key in keys:
            await self._close(key)

    def size(self):
        with self._lock:
            return len(self._items)


pool = ClientPool()


def close_idle_clients():
    """Fon vazifasi uchun: bo'sh turgan ulanishlarni yopadi."""
    if is_demo():
        return 0
    try:
        return _loop.run(pool.close_idle(), timeout=60)
    except Exception:
        return 0


def open_connections():
    return pool.size()


# ---------------------------------------------------------------- login
class LoginStore:
    """Ulanish jarayonidagi vaqtinchalik klientlar (telefon -> kod -> parol)."""

    TTL = 10 * 60

    def __init__(self):
        self.items = {}
        self.lock = threading.Lock()

    def put(self, data):
        token = secrets.token_urlsafe(24)
        with self.lock:
            self._gc()
            self.items[token] = dict(data, created=time.time())
        return token

    def get(self, token):
        with self.lock:
            self._gc()
            return self.items.get(token)

    def drop(self, token, disconnect=True):
        with self.lock:
            item = self.items.pop(token, None)
        if item and disconnect and item.get("client"):
            try:
                _loop.run(item["client"].disconnect(), timeout=20)
            except Exception:
                pass
        return item

    def _gc(self):
        dead = [k for k, v in self.items.items() if time.time() - v["created"] > self.TTL]
        for key in dead:
            item = self.items.pop(key, None)
            if item and item.get("client"):
                try:
                    asyncio.run_coroutine_threadsafe(
                        item["client"].disconnect(), _loop.ensure()
                    )
                except Exception:
                    pass


login_store = LoginStore()


class TgError(Exception):
    """Foydalanuvchiga ko'rsatiladigan xatolik.

    `wait` — Telegram belgilagan kutish vaqti (soniya). Nol bo'lmasa,
    interfeys shu muddat tugaguncha qayta urinishga yo'l qo'ymaydi.
    """

    def __init__(self, message, wait=0):
        super().__init__(message)
        self.wait = int(wait or 0)


# ---------- 1-qadam: kod yuborish ----------
def send_login_code(phone):
    """Telegram'ga kirish kodini yuboradi. Qaytaradi: token."""
    if is_demo():
        return login_store.put({"demo": True, "phone": phone, "stage": "code"})

    async def _work():
        client = _client_from_session()
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
        except errors.PhoneNumberInvalidError:
            await client.disconnect()
            raise TgError("Telefon raqami noto'g'ri")
        except errors.PhoneNumberBannedError:
            await client.disconnect()
            raise TgError("Bu raqam Telegram tomonidan bloklangan")
        except errors.PhoneNumberFloodError:
            await client.disconnect()
            raise TgError("Bu raqamga juda ko'p kod yuborilgan. Bir necha soatdan keyin urining")
        except errors.SendCodeUnavailableError:
            await client.disconnect()
            raise TgError(
                "Telegram bu raqamga kod yuborish limitini tugatdi. "
                "15-20 daqiqa kutib, qaytadan urinib ko'ring"
            )
        except errors.FloodWaitError as exc:
            await client.disconnect()
            from core.utils import human_seconds

            raise TgError(
                "Telegram bu raqamni vaqtincha cheklab qo'ydi. "
                "Qayta urinish uchun {} kutish kerak".format(
                    human_seconds(exc.seconds)
                ),
                wait=exc.seconds,
            )
        except errors.ApiIdInvalidError:
            await client.disconnect()
            raise TgError("TELEGRAM_API_ID yoki TELEGRAM_API_HASH noto'g'ri (.env)")
        return client, sent.phone_code_hash

    client, code_hash = _loop.run(_work(), timeout=120)
    return login_store.put(
        {"client": client, "phone": phone, "hash": code_hash, "stage": "code"}
    )


# ---------- 2-qadam: kodni tasdiqlash ----------
def confirm_login_code(token, code):
    """Kodni tekshiradi.

    Qaytaradi: (status, ma'lumot)
      ('ok', {...})        -> ulandi
      ('password', None)   -> 2FA parol kerak
    """
    item = login_store.get(token)
    if not item:
        raise TgError("Sessiya muddati tugadi. Qaytadan boshlang")

    # MUHIM: bo'sh kod bilan sign_in chaqirilsa, Telethon uni "kodni qayta
    # yubor" deb tushunadi va Telegram'ning qayta yuborish limitini yoqib
    # yuboradi. Shuning uchun kodni oldindan tekshiramiz.
    digits = re.sub(r"\D", "", str(code or ""))
    if not digits:
        raise TgError("Tasdiqlash kodini kiriting")
    if len(digits) < 5:
        raise TgError("Kod 5 xonali bo'lishi kerak")

    if item.get("demo"):
        if digits not in ("00000", "11111", "12345"):
            raise TgError("Demo rejimda kod: 12345")
        info = _demo_account(item["phone"])
        login_store.drop(token)
        return "ok", info

    async def _work():
        client = item["client"]
        try:
            await client.sign_in(
                phone=item["phone"], code=digits, phone_code_hash=item["hash"]
            )
        except errors.SessionPasswordNeededError:
            return "password", None
        except (errors.PhoneCodeInvalidError, errors.PhoneCodeEmptyError):
            raise TgError("Kod noto'g'ri. Telegram ilovasidagi kodni tekshiring")
        except errors.PhoneCodeExpiredError:
            raise TgError("Kod muddati tugadi. «Bekor qilish» bosib qaytadan boshlang")
        except errors.SendCodeUnavailableError:
            raise TgError(
                "Telegram bu raqamga kod yuborish limitini tugatdi. "
                "15-20 daqiqa kutib, qaytadan boshlang"
            )
        except errors.FloodWaitError as exc:
            from core.utils import human_seconds

            raise TgError(
                "Telegram vaqtincha cheklab qo'ydi. {} kutish kerak".format(
                    human_seconds(exc.seconds)
                ),
                wait=exc.seconds,
            )
        except errors.PhoneNumberUnoccupiedError:
            raise TgError("Bu raqamda Telegram akkaunti yo'q")
        except Exception as exc:
            log.exception("sign_in xatosi")
            raise TgError("Telegram xatosi: {}".format(str(exc)[:150]))
        return "ok", await _collect_account(client)

    status, info = _loop.run(_work(), timeout=120)
    if status == "ok":
        # Klient sessiya qatoriga ko'chirildi, ulanishni yopamiz
        login_store.drop(token)
    else:
        item["stage"] = "password"
    return status, info


# ---------- 3-qadam: 2FA parol ----------
def confirm_login_password(token, password):
    item = login_store.get(token)
    if not item:
        raise TgError("Sessiya muddati tugadi. Qaytadan boshlang")

    if not (password or "").strip():
        raise TgError("Parolni kiriting")

    if item.get("demo"):
        info = _demo_account(item["phone"])
        login_store.drop(token)
        return info

    async def _work():
        client = item["client"]
        try:
            await client.sign_in(password=password)
        except errors.PasswordHashInvalidError:
            raise TgError("Parol noto'g'ri")
        except errors.FloodWaitError as exc:
            raise TgError("Juda ko'p urinish. {} soniya kuting".format(exc.seconds))
        except Exception as exc:
            log.exception("2FA xatosi")
            raise TgError("Telegram xatosi: {}".format(str(exc)[:150]))
        return await _collect_account(client)

    info = _loop.run(_work(), timeout=120)
    login_store.drop(token)
    return info


async def _collect_account(client):
    me = await client.get_me()
    session_string = client.session.save()
    full_name = (me.first_name or "").strip()
    if me.last_name:
        full_name = (full_name + " " + me.last_name).strip()
    return {
        "session": session_string,
        "tg_user_id": str(me.id),
        "username": me.username or "",
        "first_name": full_name,
        "phone": "+" + str(me.phone) if me.phone else "",
        "demo": False,
    }


def _demo_account(phone):
    return {
        "session": "DEMO:" + secrets.token_hex(16),
        "tg_user_id": str(random.randint(10**8, 10**9)),
        "username": "demo_user",
        "first_name": "Demo akkaunt",
        "phone": phone,
        "demo": True,
    }


# ---------------------------------------------------------------- guruhlar
def fetch_groups(session_string, limit=500):
    """Akkaunt a'zo bo'lgan guruhlar ro'yxati."""
    if _is_demo_session(session_string):
        return _demo_groups()

    async def _work():
        client = await pool.acquire(session_string)
        if not await client.is_user_authorized():
            raise TgError("Akkaunt avtorizatsiyadan chiqib ketgan. Qayta ulang")
        out = []
        async for dialog in client.iter_dialogs(limit=limit):
            entity = dialog.entity
            is_group = dialog.is_group or (
                isinstance(entity, Channel) and getattr(entity, "megagroup", False)
            )
            if not is_group:
                continue
            if getattr(entity, "left", False) or getattr(entity, "deactivated", False):
                continue
            out.append(
                {
                    "chat_id": str(entity.id),
                    "title": getattr(entity, "title", "") or "",
                    "username": getattr(entity, "username", "") or "",
                    "members": getattr(entity, "participants_count", 0) or 0,
                    "restricted": bool(getattr(entity, "restricted", False)),
                }
            )
        return out

    return _loop.run(_work(), timeout=240)


def _demo_groups():
    names = [
        "Toshkent E'lonlar", "Avto Bozor UZ", "Ish o'rinlari 24/7",
        "Chilonzor Savdo", "Samarqand Reklama", "Biznes Networking",
        "Arenda Kvartira TSHKNT", "Farg'ona Bozor", "Buxoro E'lon",
        "IT Vakansiya UZ", "Qurilish Materiallari", "Xizmatlar Bozori",
    ]
    return [
        {
            "chat_id": str(-1000000000000 - i),
            "title": name,
            "username": "",
            "members": random.randint(400, 25000),
            "restricted": False,
        }
        for i, name in enumerate(names)
    ]


# ---------------------------------------------------------------- yuborish
class SendResult:
    __slots__ = ("ok", "error", "code", "wait")

    def __init__(self, ok, error="", code="", wait=0):
        self.ok = ok
        self.error = error
        self.code = code      # flood | banned | muted | slowmode | invalid | other
        self.wait = wait      # FloodWait soniyalari


def send_message(session_string, chat_id, text, parse_mode="html", media_path=None):
    """Bitta guruhga xabar yuboradi."""
    if _is_demo_session(session_string):
        time.sleep(random.uniform(0.15, 0.5))
        if random.random() < 0.06:
            return SendResult(False, "Demo: guruhda yozish taqiqlangan", "muted")
        return SendResult(True)

    async def _work():
        try:
            client = await pool.acquire(session_string)
            if not await client.is_user_authorized():
                return SendResult(False, "Sessiya bekor qilingan", "invalid")

            try:
                entity = await client.get_entity(int(chat_id))
            except (ValueError, TypeError):
                entity = await client.get_entity(chat_id)

            mode = parse_mode if parse_mode == "html" else None
            if media_path and os.path.exists(media_path):
                await client.send_file(entity, media_path, caption=text, parse_mode=mode)
            else:
                await client.send_message(
                    entity, text, link_preview=False, parse_mode=mode
                )
            return SendResult(True)

        except errors.FloodWaitError as exc:
            return SendResult(False, "FloodWait {}s".format(exc.seconds), "flood", exc.seconds)
        except errors.SlowModeWaitError as exc:
            return SendResult(False, "SlowMode {}s".format(exc.seconds), "slowmode", exc.seconds)
        except errors.ChatWriteForbiddenError:
            return SendResult(False, "Guruhda yozish taqiqlangan", "muted")
        except errors.UserBannedInChannelError:
            return SendResult(False, "Akkaunt guruhdan bloklangan", "banned")
        except errors.ChannelPrivateError:
            return SendResult(False, "Guruh yopiq yoki chiqarib yuborilgan", "removed")
        except errors.PeerIdInvalidError:
            return SendResult(False, "Guruh topilmadi", "invalid")
        except errors.UserDeactivatedBanError:
            return SendResult(False, "Akkaunt Telegram tomonidan bloklangan", "account_banned")
        except errors.AuthKeyUnregisteredError:
            await pool.drop(session_string)
            return SendResult(False, "Sessiya bekor qilingan", "invalid")
        except errors.MessageTooLongError:
            return SendResult(False, "Xabar juda uzun", "other")
        except Exception as exc:
            return SendResult(False, str(exc)[:200], "other")

    try:
        return _loop.run(_work(), timeout=120)
    except Exception as exc:
        return SendResult(False, str(exc)[:200], "other")


def check_session(session_string):
    """Sessiya hali amal qiladimi?"""
    if _is_demo_session(session_string):
        return True

    async def _work():
        client = await pool.acquire(session_string)
        return await client.is_user_authorized()

    try:
        return bool(_loop.run(_work(), timeout=60))
    except Exception:
        return False


def logout_session(session_string):
    """Telegram sessiyasini bekor qiladi va ulanishni yopadi."""
    if _is_demo_session(session_string):
        return True

    async def _work():
        try:
            client = await pool.acquire(session_string)
            await client.log_out()
            return True
        finally:
            await pool.drop(session_string)

    try:
        return bool(_loop.run(_work(), timeout=60))
    except Exception:
        return False
