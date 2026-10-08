#!/usr/bin/env bash
# ============================================================
#  AutoXabar — zaxiradan tiklash
#
#      ./scripts/restore.sh backups/autoxabar-2026-10-08-040000.tar.gz
#
#  Hozirgi baza, Telegram sessiyalari va rasmlar arxivdagi holatga
#  almashtiriladi. Oldin hozirgi holatdan ham zaxira olinadi — xato
#  arxiv tanlansa, orqaga qaytish mumkin.
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

die() { printf '\033[31mXATO: %s\033[0m\n' "$*" >&2; exit 1; }

archive=${1:-}
[ -n "$archive" ] && [ -f "$archive" ] \
    || die "foydalanish: ./scripts/restore.sh backups/autoxabar-....tar.gz"
gzip -t "$archive" 2>/dev/null || die "arxiv buzilgan: $archive"
# grep -q ishlatilmaydi: u erta chiqsa tar SIGPIPE oladi va pipefail xato beradi
tar tzf "$archive" | grep -x 'autoxabar.db' >/dev/null || die "arxivda autoxabar.db yo'q"

echo "Arxiv: $archive"
echo "Hozirgi baza, sessiyalar va rasmlar shu arxivdagi holatga almashtiriladi."
read -r -p "Davom etilsinmi? (ha/yo'q): " answer
[ "$answer" = "ha" ] || { echo "Bekor qilindi."; exit 1; }

# Arxiv vaqtinchalik nusxadan o'qiladi: quyidagi zaxira yoki rotatsiya
# asl faylga tegib ketsa ham tiklash buzilmaydi.
copy=$(mktemp)
trap 'rm -f "$copy"' EXIT
cp "$archive" "$copy"

echo "== Hozirgi holatdan zaxira"
./scripts/backup.sh

echo "== Konteynerlar to'xtatilmoqda"
docker compose down

echo "== Tiklanmoqda"
# Avval arxiv to'liq ochiladi, faqat shundan keyin eski ma'lumot o'chiriladi
docker compose run --rm --no-deps -T autoxabar sh -c '
set -e
rm -rf /tmp/r && mkdir -p /tmp/r
tar xzf - -C /tmp/r
test -s /tmp/r/autoxabar.db
rm -f /data/autoxabar.db /data/autoxabar.db-wal /data/autoxabar.db-shm
find /data/sessions -mindepth 1 -delete
find /app/static/uploads -mindepth 1 -delete
cp /tmp/r/autoxabar.db /data/
[ -d /tmp/r/sessions ] && cp -a /tmp/r/sessions/. /data/sessions/
[ -d /tmp/r/uploads ] && cp -a /tmp/r/uploads/. /app/static/uploads/
rm -rf /tmp/r
' < "$copy"

echo "== Qayta ishga tushirilmoqda"
./scripts/deploy.sh
