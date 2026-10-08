#!/usr/bin/env bash
# ============================================================
#  AutoXabar — zaxira nusxa
#
#      ./scripts/backup.sh
#
#  backups/autoxabar-YYYY-MM-DD-HHMMSS.tar.gz ichida:
#      autoxabar.db   SQLite bazasi (ishlab turgan paytda ham butun
#                     holatda — sqlite3 backup API orqali olinadi)
#      sessions/      Telegram sessiyalari
#      uploads/       foydalanuvchi yuklagan rasmlar
#
#  DIQQAT: sessiyalar Telegram akkauntlariga to'liq kirish beradi.
#  Arxivlar faqat egasiga o'qiladi (600) — serverdan tashqariga
#  shifrlanmagan holda ko'chirmang.
#
#  Eng oxirgi BACKUP_KEEP ta (sukut: 14) arxiv saqlanadi.
#
#  Har kuni 04:00 da (crontab -e):
#      0 4 * * * cd /opt/autoxabar && ./scripts/backup.sh >> backups/backup.log 2>&1
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

KEEP=${BACKUP_KEEP:-14}
DIR=backups
umask 077
mkdir -p "$DIR"

out="$DIR/autoxabar-$(date +%F-%H%M%S).tar.gz"
tmp="$out.part"

# Konteyner ichida bajariladi: bazaning izchil nusxasi + arxiv stdout'ga
inner='
set -e
python - <<PY
import sqlite3
src = sqlite3.connect("/data/autoxabar.db")
dst = sqlite3.connect("/tmp/autoxabar.db")
src.backup(dst)
dst.close()
src.close()
PY
tar czf - -C /tmp autoxabar.db -C /data sessions -C /app/static uploads
rm -f /tmp/autoxabar.db
'

make_archive() {
    if [ -n "$(docker compose ps -q --status running autoxabar 2>/dev/null)" ]; then
        docker compose exec -T autoxabar sh -c "$inner"
    else
        # Ilova to'xtagan: vaqtinchalik konteynerda o'sha volume'lar bilan
        docker compose run --rm --no-deps -T autoxabar sh -c "$inner"
    fi
}

# Bo'sh yoki buzilgan arxiv eski nusxalarni o'chirib yubormasligi kerak
if ! make_archive > "$tmp" || [ ! -s "$tmp" ] || ! gzip -t "$tmp" 2>/dev/null; then
    rm -f "$tmp"
    echo "XATO: zaxira olinmadi" >&2
    exit 1
fi
mv "$tmp" "$out"
echo "$(date '+%F %T')  zaxira: $out ($(du -h "$out" | cut -f1))"

# Eskilarini tozalash
ls -1t "$DIR"/autoxabar-*.tar.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
    rm -f -- "$old"
done
