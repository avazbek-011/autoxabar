# -*- coding: utf-8 -*-
"""Ochiq sahifalarni statik HTML ga aylantiradi (GitHub Pages uchun).

Nima uchun kerak: GitHub Pages Python serverini ishlata olmaydi, faqat tayyor
HTML fayllarni ko'rsatadi. Shuning uchun bosh sahifa, narxlar, qo'llanma va
hujjatlar oldindan render qilinib `docs/` papkasiga yoziladi.

Kabinet va admin panel serversiz ishlamaydi — ulardagi tugmalar haqiqiy
dastur manziliga (APP_URL) yo'naltiriladi.

Ishlatish:
    python build_static.py                       # tugmalar Telegram botga
    python build_static.py https://sayt.uz       # tugmalar haqiqiy saytga
"""
import os
import re
import shutil
import sys

os.environ.setdefault("RUN_SCHEDULER", "0")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "docs")

# Statik holga keltiriladigan sahifalar: yo'l -> fayl nomi
PAGES = {
    "/": "index.html",
    "/narxlar": "narxlar.html",
    "/qollanma": "qollanma.html",
    "/aloqa": "aloqa.html",
    "/oferta": "oferta.html",
    "/maxfiylik": "maxfiylik.html",
}

# Server talab qiladigan bo'limlar — haqiqiy dastur manziliga yo'naltiriladi
APP_ROUTES = [
    "/kabinet", "/kirish", "/royxatdan-otish", "/parolni-tiklash",
    "/admin", "/chiqish", "/tolov",
]


NOTICE_PAGE = """<!DOCTYPE html>
<html lang="uz"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Xizmat tez orada — VIPADSUZ</title>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="static/css/app.css">
<link rel="icon" href="static/img/logo.svg" type="image/svg+xml">
</head><body>
<div class="auth-wrap"><div class="auth-card center">
  <img src="static/img/logo.svg" width="62" height="62" alt="VIPADSUZ" style="margin:0 auto 18px">
  <h2 class="mb">Ro&#8216;yxatdan o&#8216;tish tez orada</h2>
  <p class="muted mb-lg">
    Bu sahifa &mdash; xizmatning tanishtiruv ko&#8216;rinishi. Ro&#8216;yxatdan o&#8216;tish va
    akkaunt ulash uchun xizmat serverda ishga tushirilishi kerak.
    Ishga tushishi haqida xabar beramiz.
  </p>
  <a href="{{HOME}}" class="btn btn-primary btn-block">Bosh sahifaga qaytish</a>
  <div class="auth-foot"><a href="aloqa.html">Aloqa</a> &middot; <a href="narxlar.html">Narxlar</a></div>
</div></div>
</body></html>
"""


def rewrite(html, app_url):
    """Havolalarni statik saytga moslaydi."""
    # 1) Statik fayllar: /static/... -> static/...  (nisbiy yo'l)
    html = html.replace('href="/static/', 'href="static/')
    html = html.replace('src="/static/', 'src="static/')
    html = re.sub(r'url_for[^"]*', "", html)  # ehtiyot chorasi

    # 2) Serverga bog'liq bo'limlar -> haqiqiy dastur manzili
    for route in APP_ROUTES:
        html = re.sub(
            r'href="' + re.escape(route) + r'(/[^"]*)?"',
            'href="{}"'.format(app_url),
            html,
        )

    # 3) Ichki sahifalar: /narxlar -> narxlar.html
    for path, filename in PAGES.items():
        if path == "/":
            continue
        html = html.replace('href="{}"'.format(path), 'href="{}"'.format(filename))
        html = html.replace('href="{}#'.format(path), 'href="{}#'.format(filename))

    # 4) Bosh sahifa
    html = html.replace('href="/"', 'href="index.html"')
    html = html.replace('href="/#', 'href="index.html#')

    # 5) Jonli statistika endpointi statik saytda yo'q — o'chiramiz
    html = re.sub(r'\sdata-live="[^"]*"', "", html)
    html = re.sub(r'\sdata-every="[^"]*"', "", html)

    return html


def main():
    # Haqiqiy dastur manzili berilmasa, tugmalar tushuntirish sahifasiga boradi
    app_url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "kirish.html"

    from app import app

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    # --- Sahifalarni render qilamiz ---
    app.config["SERVER_NAME"] = None
    with app.test_client() as client:
        for path, filename in PAGES.items():
            resp = client.get(path)
            if resp.status_code != 200:
                print("  XATO {} -> HTTP {}".format(path, resp.status_code))
                continue
            html = rewrite(resp.get_data(as_text=True), app_url)
            with open(os.path.join(OUT, filename), "w", encoding="utf-8") as fh:
                fh.write(html)
            print("  {:<14} -> docs/{}  ({} KB)".format(
                path, filename, len(html) // 1024))

    # --- Statik fayllar (uploads'siz) ---
    src = os.path.join(BASE, "static")
    dst = os.path.join(OUT, "static")
    shutil.copytree(
        src, dst,
        ignore=shutil.ignore_patterns("uploads", "*.pyc", "__pycache__"),
    )
    print("  static/        -> docs/static/")

    # --- Dastur manzili yo'q bo'lsa, tushuntirish sahifasi ---
    if app_url == "kirish.html":
        notice = NOTICE_PAGE.replace("{{HOME}}", "index.html")
        with open(os.path.join(OUT, "kirish.html"), "w", encoding="utf-8") as fh:
            fh.write(notice)
        print("  {:<14} -> docs/kirish.html".format("(tushuntirish)"))

    # --- Jekyll bu papkani qayta ishlamasin ---
    open(os.path.join(OUT, ".nojekyll"), "w").close()

    # --- 404 sahifasi ---
    shutil.copy(os.path.join(OUT, "index.html"), os.path.join(OUT, "404.html"))

    print()
    print("  Tayyor: docs/  ({} ta fayl)".format(
        sum(len(f) for _, _, f in os.walk(OUT))))
    print("  Tugmalar yo'naltiriladi: {}".format(app_url))


if __name__ == "__main__":
    main()
