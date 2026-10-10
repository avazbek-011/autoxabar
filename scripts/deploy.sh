#!/usr/bin/env bash
# ============================================================
#  AutoXabar — serverga joylashtirish / yangilash
#
#  Repozitoriy ildizidan ishga tushiriladi:
#      ./scripts/deploy.sh
#
#  Birinchi marta:  .env yaratadi (SECRET_KEY va ADMIN_PASSWORD
#                   tasodifiy), to'xtaydi — .env ni tekshirib,
#                   qayta ishga tushirasiz.
#  Keyingi safar:   .env ni tekshiradi, zaxira oladi, konteynerlarni
#                   qayta yig'ib ko'taradi va sog'lig'ini kutadi.
#
#  Yangilash:  git pull && ./scripts/deploy.sh
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

red()    { printf '\033[31m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
die()    { red "XATO: $*"; exit 1; }

# .env dagi qiymatni o'qiydi: izoh, bo'sh joy va qo'shtirnoqsiz
env_get() {
    local line
    line=$(grep -E "^$1=" .env | tail -n 1 || true)
    line=${line#*=}
    line=$(printf '%s' "$line" | sed -E 's/[[:space:]]+#.*$//; s/^[[:space:]]+//; s/[[:space:]]+$//')
    line=${line%\"}; line=${line#\"}
    line=${line%\'}; line=${line#\'}
    printf '%s' "$line"
}

# .env dagi qiymatni almashtiradi (qiymat faqat [A-Za-z0-9_-] bo'lishi kerak)
env_set() {
    if grep -qE "^$1=" .env; then
        sed -i -E "s|^$1=.*$|$1=$2|" .env
    else
        printf '%s=%s\n' "$1" "$2" >> .env
    fi
}

random_token() {
    # head yetarlicha o'qigach quvurni yopadi va tr SIGPIPE oladi —
    # bu xato emas, shuning uchun pipefail shu yerda o'chiriladi.
    ( set +o pipefail; LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom 2>/dev/null | head -c "$1" )
}

# ------------------------------------------------------------ 1. Docker
command -v docker >/dev/null 2>&1 \
    || die "Docker o'rnatilmagan. O'rnatish: curl -fsSL https://get.docker.com | sh"
docker compose version >/dev/null 2>&1 \
    || die "'docker compose' (v2) topilmadi. docker-compose-plugin paketini o'rnating."

# env_file'dagi `required: false` uchun Compose 2.24+ kerak
compose_ver=$(docker compose version --short 2>/dev/null | sed 's/^v//')
if [ "$(printf '%s\n2.24.0\n' "$compose_ver" | sort -V | head -n 1)" != "2.24.0" ]; then
    die "Docker Compose $compose_ver eski — kamida 2.24 kerak."
fi

# ------------------------------------------------------------ 2. .env
if [ ! -f .env ]; then
    secret=$(random_token 64)
    admin_pass=$(random_token 20)
    [ ${#secret} -eq 64 ] && [ ${#admin_pass} -eq 20 ] || die "tasodifiy kalit yaratilmadi"

    umask 077
    cp .env.example .env
    env_set SECRET_KEY "$secret"
    env_set ADMIN_PASSWORD "$admin_pass"
    env_set BASE_URL "https://avtoxabar.vipads.uz"
    env_set FLASK_DEBUG "0"

    green ".env yaratildi (huquqlar: 600)."
    echo
    echo "  Admin paroli: $admin_pass"
    echo "  (u .env ichida ham saqlandi)"
    echo
    yellow "Endi .env ni tahrirlang va qayta ishga tushiring:"
    echo "  - ADMIN_PHONE          o'z raqamingiz"
    echo "  - TELEGRAM_API_ID/HASH my.telegram.org dan (bo'lmasa DEMO rejim)"
    echo "  - PAYMENT_HUB_*        hub administratoridan (URL, API kaliti, webhook siri)"
    echo
    echo "  nano .env && ./scripts/deploy.sh"
    exit 0
fi

errors=0
warn() { yellow "  ! $*"; }
fail() { red "  x $*"; errors=$((errors + 1)); }

echo "== .env tekshirilmoqda"
[ "$(stat -c %a .env 2>/dev/null || echo 600)" = "600" ] \
    || warn ".env boshqalarga ham o'qiladi — 'chmod 600 .env' qiling"

secret=$(env_get SECRET_KEY)
[ ${#secret} -ge 32 ] || fail "SECRET_KEY bo'sh yoki juda qisqa (kamida 32 belgi)"

[ -n "$(env_get ADMIN_PASSWORD)" ] || fail "ADMIN_PASSWORD bo'sh"
[ "$(env_get ADMIN_PHONE)" != "+998900000000" ] \
    || warn "ADMIN_PHONE hali standart qiymatda (+998900000000)"

case "$(env_get FLASK_DEBUG)" in
    1|true|True) fail "FLASK_DEBUG=1 — serverda 0 bo'lishi shart" ;;
esac

base_url=$(env_get BASE_URL)
case "$base_url" in
    https://*) ;;
    *) warn "BASE_URL https emas ($base_url) — to'lovdan qaytish havolasi (return_url) buziladi" ;;
esac

[ -n "$(env_get TELEGRAM_API_ID)" ] && [ -n "$(env_get TELEGRAM_API_HASH)" ] \
    || warn "TELEGRAM_API_ID/HASH bo'sh — xabarlar yuborilmaydi (DEMO rejim)"

for k in PAYMENT_HUB_URL PAYMENT_HUB_API_KEY PAYMENT_HUB_WEBHOOK_SECRET; do
    [ -n "$(env_get "$k")" ] || { warn "$k bo'sh — to'lov qabul qilinmaydi"; break; }
done
[ "$(env_get PAYMENT_HUB_PROVIDER)" != "mock" ]     || warn "PAYMENT_HUB_PROVIDER=mock — haqiqiy to'lov olinmaydi (faqat sinov hub'i)"

[ "$errors" -eq 0 ] || die ".env da $errors ta xato bor — tuzatib, qayta ishga tushiring."

# ------------------------------------------------------------ 3. Zaxira
# Yangilashdan oldin — agar ilova allaqachon ishlayotgan bo'lsa
if [ -n "$(docker compose ps -q --status running autoxabar 2>/dev/null)" ]; then
    echo "== Yangilashdan oldin zaxira olinmoqda"
    ./scripts/backup.sh
fi

# ------------------------------------------------------------ 4. Ishga tushirish
echo "== Konteynerlar yig'ilmoqda va ishga tushirilmoqda"
# nginx `service_healthy` ga bog'langan, shuning uchun bu buyruq ilova
# sog'lom bo'lguncha kutadi (healthcheck oralig'i 30 s).
if ! docker compose up -d --build --remove-orphans; then
    docker compose logs --tail 60 autoxabar || true
    die "konteynerlar ishga tushmadi. Yuqoridagi loglarga qarang."
fi

echo "== Ilova sog'lig'i kutilmoqda"
for _ in $(seq 1 30); do
    status=$(docker inspect -f '{{.State.Health.Status}}' autoxabar 2>/dev/null || echo "?")
    [ "$status" = "healthy" ] && break
    sleep 3
done
if [ "$status" != "healthy" ]; then
    docker compose logs --tail 60 autoxabar
    die "ilova sog'lom holatga kelmadi (holat: $status). Yuqoridagi loglarga qarang."
fi

port=$(env_get APP_PORT); port=${port:-8080}
if command -v curl >/dev/null 2>&1; then
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/" || true)
    [ "$code" = "200" ] || die "nginx orqali 127.0.0.1:$port javob bermadi (HTTP $code)"
fi

echo
green "Tayyor: ilova 127.0.0.1:$port da ishlayapti."
echo "  Loglar:  docker compose logs -f autoxabar"
echo "  Sayt:    $base_url"
