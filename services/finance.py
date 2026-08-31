"""Moliya moduli.

Hisob-kitob mantiqi (har bir to'lov uchun):

    yalpi tushum (gross)
      - Payme ekvayring komissiyasi (acquiring_percent %)
      = hisobga tushgan summa (net_receipt)
      - soliq (tax_percent %  — sukut bo'yicha 10%)
      = SOF FOYDA (net)  ->  bankdan yechib olinadigan summa

Oylik hisobot `month_report()` orqali olinadi; `available_to_withdraw()`
hozirda yechib olish mumkin bo'lgan qoldiqni qaytaradi.
"""
from datetime import timedelta

from core.db import (
    execute,
    get_setting_float,
    month_str,
    now,
    now_str,
    query,
    scalar,
    today_str,
)

DEFAULT_TAX = 10.0
DEFAULT_FEE = 1.0

EXPENSE_CATEGORIES = {
    "server": "Server / hosting",
    "reklama": "Reklama",
    "ish_haqi": "Ish haqi",
    "telegram": "Telegram / API",
    "other": "Boshqa",
}


def tax_percent(db=None):
    return get_setting_float("tax_percent", DEFAULT_TAX, db=db)


def fee_percent(db=None):
    return get_setting_float("acquiring_percent", DEFAULT_FEE, db=db)


def split(gross, tax_pct=None, fee_pct=None, db=None):
    """Bitta summani tarkibiy qismlarga ajratadi."""
    gross = int(round(float(gross or 0)))
    tax_pct = tax_percent(db=db) if tax_pct is None else float(tax_pct)
    fee_pct = fee_percent(db=db) if fee_pct is None else float(fee_pct)

    fee = int(round(gross * fee_pct / 100.0))
    receipt = gross - fee
    tax = int(round(receipt * tax_pct / 100.0))
    net = receipt - tax
    return {
        "gross": gross,
        "acquiring_fee": fee,
        "receipt": receipt,
        "tax": tax,
        "net": net,
        "tax_percent": tax_pct,
        "fee_percent": fee_pct,
    }


# ---------------------------------------------------------------- daftar
def record_revenue(payment_id, db=None):
    """To'langan buyurtmani moliya daftariga yozadi (idempotent)."""
    payment = query("SELECT * FROM payments WHERE id = ?", (payment_id,), one=True, db=db)
    if not payment or payment["status"] != "paid":
        return None

    exists = query(
        "SELECT id FROM finance_ledger WHERE payment_id = ?", (payment_id,), one=True, db=db
    )
    if exists:
        return exists["id"]

    parts = split(payment["amount"], db=db)
    paid_at = payment["paid_at"] or now_str()
    day = str(paid_at)[:10]

    return execute(
        "INSERT INTO finance_ledger(day, month, payment_id, user_id, gross, "
        "acquiring_fee, tax, net, tax_percent, fee_percent, note, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            day,
            day[:7],
            payment_id,
            payment["user_id"],
            parts["gross"],
            parts["acquiring_fee"],
            parts["tax"],
            parts["net"],
            parts["tax_percent"],
            parts["fee_percent"],
            payment["description"] or "",
            now_str(),
        ),
        db=db,
    )


def _sum_ledger(where="", params=(), db=None):
    row = query(
        "SELECT COALESCE(SUM(gross),0) AS gross, "
        "COALESCE(SUM(acquiring_fee),0) AS fee, "
        "COALESCE(SUM(tax),0) AS tax, "
        "COALESCE(SUM(net),0) AS net, "
        "COUNT(*) AS cnt FROM finance_ledger " + (("WHERE " + where) if where else ""),
        params,
        one=True,
        db=db,
    )
    return {
        "gross": row["gross"],
        "fee": row["fee"],
        "tax": row["tax"],
        "net": row["net"],
        "count": row["cnt"],
        "receipt": row["gross"] - row["fee"],
    }


# ---------------------------------------------------------------- hisobot
def month_report(month=None, db=None):
    """Bir oylik to'liq moliyaviy hisobot."""
    month = month or month_str()
    base = _sum_ledger("month = ?", (month,), db=db)

    expenses = scalar(
        "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE month = ?", (month,), db=db
    )
    paid_net = scalar(
        "SELECT COALESCE(SUM(amount),0) FROM payouts WHERE month = ? AND kind = 'net'",
        (month,),
        db=db,
    )
    paid_tax = scalar(
        "SELECT COALESCE(SUM(amount),0) FROM payouts WHERE month = ? AND kind = 'tax'",
        (month,),
        db=db,
    )

    profit = base["net"] - expenses  # xarajatlardan keyingi sof foyda

    return {
        "month": month,
        "month_label": month_label(month),
        "gross": base["gross"],
        "fee": base["fee"],
        "receipt": base["receipt"],
        "tax": base["tax"],
        "net": base["net"],
        "expenses": expenses,
        "profit": profit,
        "payments_count": base["count"],
        "withdrawn_net": paid_net,
        "withdrawn_tax": paid_tax,
        "remaining_net": profit - paid_net,
        "remaining_tax": base["tax"] - paid_tax,
        "tax_percent": tax_percent(db=db),
        "fee_percent": fee_percent(db=db),
        "avg_check": int(base["gross"] / base["count"]) if base["count"] else 0,
    }


def totals(db=None):
    """Butun davr bo'yicha yig'indi."""
    base = _sum_ledger(db=db)
    expenses = scalar("SELECT COALESCE(SUM(amount),0) FROM expenses", db=db)
    paid_net = scalar(
        "SELECT COALESCE(SUM(amount),0) FROM payouts WHERE kind = 'net'", db=db
    )
    paid_tax = scalar(
        "SELECT COALESCE(SUM(amount),0) FROM payouts WHERE kind = 'tax'", db=db
    )
    profit = base["net"] - expenses
    return {
        "gross": base["gross"],
        "fee": base["fee"],
        "receipt": base["receipt"],
        "tax": base["tax"],
        "net": base["net"],
        "expenses": expenses,
        "profit": profit,
        "payments_count": base["count"],
        "withdrawn_net": paid_net,
        "withdrawn_tax": paid_tax,
        "available": profit - paid_net,
        "tax_due": base["tax"] - paid_tax,
    }


def available_to_withdraw(db=None):
    """Hozir bankdan yechib olish mumkin bo'lgan sof summa."""
    return totals(db=db)["available"]


def today_revenue(db=None):
    return _sum_ledger("day = ?", (today_str(),), db=db)


def period_revenue(days=30, db=None):
    frm = (now() - timedelta(days=days)).strftime("%Y-%m-%d")
    return _sum_ledger("day >= ?", (frm,), db=db)


def daily_series(days=30, db=None):
    """Kunlik grafik uchun ma'lumot."""
    frm = (now() - timedelta(days=days - 1)).date()
    rows = query(
        "SELECT day, SUM(gross) AS gross, SUM(net) AS net, SUM(tax) AS tax, "
        "COUNT(*) AS cnt FROM finance_ledger WHERE day >= ? GROUP BY day",
        (frm.strftime("%Y-%m-%d"),),
        db=db,
    )
    by_day = {r["day"]: r for r in rows}
    out = []
    for i in range(days):
        day = (frm + timedelta(days=i)).strftime("%Y-%m-%d")
        row = by_day.get(day)
        out.append(
            {
                "day": day,
                "label": day[8:10] + "." + day[5:7],
                "gross": row["gross"] if row else 0,
                "net": row["net"] if row else 0,
                "tax": row["tax"] if row else 0,
                "count": row["cnt"] if row else 0,
            }
        )
    return out


MONTH_NAMES = [
    "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
    "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
]

# Grafik uchun bir-biridan farq qiladigan qisqartmalar (Iyun/Iyul chalkashmasin)
MONTH_SHORT = [
    "Yan", "Fev", "Mar", "Apr", "May", "Iyn",
    "Iyl", "Avg", "Sen", "Okt", "Noy", "Dek",
]


def month_label(month):
    try:
        year, mon = month.split("-")
        return "{} {}".format(MONTH_NAMES[int(mon) - 1], year)
    except (ValueError, IndexError, AttributeError):
        return month


def monthly_series(months=12, db=None):
    """Oylik grafik: oxirgi N oy."""
    cur = now().replace(day=1)
    keys = []
    for _ in range(months):
        keys.append(cur.strftime("%Y-%m"))
        cur = (cur - timedelta(days=1)).replace(day=1)
    keys.reverse()

    rows = query(
        "SELECT month, SUM(gross) AS gross, SUM(net) AS net, SUM(tax) AS tax, "
        "COUNT(*) AS cnt FROM finance_ledger GROUP BY month",
        db=db,
    )
    by_month = {r["month"]: r for r in rows}

    payouts = query(
        "SELECT month, SUM(amount) AS amount FROM payouts WHERE kind='net' GROUP BY month",
        db=db,
    )
    paid_by_month = {r["month"]: r["amount"] for r in payouts}

    expenses = query(
        "SELECT month, SUM(amount) AS amount FROM expenses GROUP BY month", db=db
    )
    exp_by_month = {r["month"]: r["amount"] for r in expenses}

    out = []
    for key in keys:
        row = by_month.get(key)
        exp = exp_by_month.get(key, 0)
        net = row["net"] if row else 0
        out.append(
            {
                "month": key,
                "label": month_label(key),
                "short": MONTH_SHORT[int(key[5:7]) - 1],
                "gross": row["gross"] if row else 0,
                "net": net,
                "tax": row["tax"] if row else 0,
                "count": row["cnt"] if row else 0,
                "expenses": exp,
                "profit": net - exp,
                "withdrawn": paid_by_month.get(key, 0),
            }
        )
    return out


# ---------------------------------------------------------------- yozuvlar
def add_expense(category, title, amount, note="", day=None, db=None):
    day = day or today_str()
    return execute(
        "INSERT INTO expenses(day, month, category, title, amount, note, created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (day, day[:7], category, title, int(amount), note, now_str()),
        db=db,
    )


def add_payout(month, amount, kind="net", destination="", note="", user_id=None, db=None):
    """Bankdan yechib olinganini qayd etadi."""
    return execute(
        "INSERT INTO payouts(month, amount, kind, destination, note, paid_at, "
        "created_by, created_at) VALUES(?,?,?,?,?,?,?,?)",
        (month, int(amount), kind, destination, note, now_str(), user_id, now_str()),
        db=db,
    )


def payouts_list(limit=100, db=None):
    return query(
        "SELECT * FROM payouts ORDER BY paid_at DESC LIMIT ?", (limit,), db=db
    )


def expenses_list(month=None, limit=100, db=None):
    if month:
        return query(
            "SELECT * FROM expenses WHERE month = ? ORDER BY day DESC, id DESC LIMIT ?",
            (month, limit),
            db=db,
        )
    return query("SELECT * FROM expenses ORDER BY day DESC, id DESC LIMIT ?", (limit,), db=db)


def ledger_list(month=None, limit=200, db=None):
    if month:
        return query(
            "SELECT l.*, u.phone, u.name FROM finance_ledger l "
            "LEFT JOIN users u ON u.id = l.user_id "
            "WHERE l.month = ? ORDER BY l.id DESC LIMIT ?",
            (month, limit),
            db=db,
        )
    return query(
        "SELECT l.*, u.phone, u.name FROM finance_ledger l "
        "LEFT JOIN users u ON u.id = l.user_id ORDER BY l.id DESC LIMIT ?",
        (limit,),
        db=db,
    )


def known_months(db=None):
    rows = query(
        "SELECT DISTINCT month FROM finance_ledger "
        "UNION SELECT DISTINCT month FROM payouts "
        "UNION SELECT DISTINCT month FROM expenses ORDER BY 1 DESC",
        db=db,
    )
    months = [r[0] for r in rows]
    current = month_str()
    if current not in months:
        months.insert(0, current)
    return months


def rebuild_ledger(db=None):
    """Barcha to'langan buyurtmalarni daftarga qayta yozadi (yetishmaganini)."""
    rows = query(
        "SELECT p.id FROM payments p LEFT JOIN finance_ledger l ON l.payment_id = p.id "
        "WHERE p.status = 'paid' AND l.id IS NULL",
        db=db,
    )
    count = 0
    for row in rows:
        if record_revenue(row["id"], db=db):
            count += 1
    return count
