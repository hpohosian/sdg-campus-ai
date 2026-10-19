#!/usr/bin/env bash
# Restores a backup made by scripts/backup.sh.
#
#   scripts/restore.sh backups/sdg-20261019-120000
#       Test restore: builds a SEPARATE copy of the system (project "sdg-campus-restore", its own
#       volumes, database on 127.0.0.1:25432, backend on 127.0.0.1:18001), loads the backup into it
#       and checks that it answers. Your live system is not touched. This is how a backup is proven.
#
#   scripts/restore.sh backups/sdg-... --project sdg-campus-ai
#       REAL restore into the live project (disaster recovery on a fresh VM, or rolling back).
#       Overwrites the current chat database, images and index. You must type the project name.
#
#   --keep-running   leave the test copy running afterwards (default: stop it, keep its volumes)
#
# Remove a test copy completely (ONLY the test project name, never the live one):
#   docker compose -p sdg-campus-restore --env-file .env.docker down -v
set -euo pipefail
# shellcheck source=scripts/_common.sh
. "$(dirname "$0")/_common.sh"
cd "$ROOT"

BK=""; TARGET="sdg-campus-restore"; KEEP_RUNNING=0
while [ $# -gt 0 ]; do
    case "$1" in
        --project) TARGET="$2"; shift ;;
        --keep-running) KEEP_RUNNING=1 ;;
        -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*) die "Unknown option: $1 (see --help)" ;;
        *) BK="$1" ;;
    esac
    shift
done
[ -n "$BK" ] || die "Usage: scripts/restore.sh <backup folder> [--project NAME]"
[ -d "$BK" ] || die "'$BK' is not a directory."
BK="$(cd "$BK" && pwd)"

check_docker
PROJECT="$TARGET"
LIVE=0; [ "$TARGET" = "sdg-campus-ai" ] && LIVE=1

# --- verify the backup -------------------------------------------------------------
info "${C_B}1/5 Verifying checksums${C_0}"
for f in SHA256SUMS db.sql.gz env.docker MANIFEST.txt; do [ -f "$BK/$f" ] || die "$f is missing in the backup."; done
( cd "$BK" && sha256sum -c SHA256SUMS >/dev/null ) || die "Checksum mismatch - the backup is damaged. Nothing was changed."
gzip -t "$BK/db.sql.gz" || die "db.sql.gz is corrupt."
ok "backup is intact"; sed 's/^/    /' "$BK/MANIFEST.txt"

# --- environment --------------------------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
    cp "$BK/env.docker" "$ENV_FILE"; chmod 600 "$ENV_FILE"
    ok "installed $ENV_FILE from the backup (fresh machine)"
elif ! cmp -s "$ENV_FILE" "$BK/env.docker"; then
    warn "$ENV_FILE differs from the one in the backup. The CURRENT file is used"
    warn "(the database password is irrelevant for a dump; MOODLE_SECRET must match the Moodle plugin)."
fi

if [ "$LIVE" = 1 ]; then
    warn "This OVERWRITES the live chat database, chat images and ChromaDB index of project '$PROJECT'."
    [ -t 0 ] || die "Needs a terminal for the confirmation."
    read -r -p "Type the project name ($PROJECT) to continue: " ans
    [ "$ans" = "$PROJECT" ] || die "Cancelled."
    export BACKEND_HOST_PORT="${BACKEND_HOST_PORT:-8001}"
else
    export POSTGRES_HOST_PORT="${RESTORE_DB_PORT:-25432}"
    export BACKEND_HOST_PORT="${RESTORE_BACKEND_PORT:-18001}"
    # The test copy does not need Moodle's real files (they are only read while indexing), and the
    # configured path may not even be valid in this shell (e.g. "D:/..." inside WSL). An empty folder does.
    EMPTY_MD="$ROOT/.restore-empty-moodledata"
    mkdir -p "$EMPTY_MD"
    export MOODLEDATA_HOST_PATH="$EMPTY_MD"
fi
HEALTH_URL="http://127.0.0.1:${BACKEND_HOST_PORT}/health"

# --- containers + volumes -----------------------------------------------------------
info "${C_B}2/5 Preparing project '$PROJECT'${C_0}"
dc stop backend >/dev/null 2>&1 || true
dc create db backend >/dev/null
dc up -d db >/dev/null
for i in $(seq 1 40); do
    dc exec -T db sh -c 'pg_isready -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1 && break
    [ "$i" = 40 ] && die "The database does not start."
    sleep 2
done
ok "database is up"

# --- data ---------------------------------------------------------------------------------
info "${C_B}3/5 Loading the database${C_0}"
if [ "$LIVE" = 1 ]; then
    # drop leftovers so the dump (--clean) starts from a known state
    dc exec -T db sh -c 'psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"' >/dev/null
fi
gzip -dc "$BK/db.sql.gz" | dc exec -T db sh -c 'psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' >/dev/null \
    || die "Loading the dump failed."
ok "database restored"

info "${C_B}4/5 Loading images and index${C_0}"
IMG="$(helper_image)"
for v in chat_images chroma_data; do
    if [ ! -f "$BK/$v.tar.gz" ]; then warn "$v.tar.gz not in the backup - skipped"; continue; fi
    real="$(vol_name "$PROJECT" "$v")"
    [ -n "$real" ] || die "volume $v was not created."
    docker run --rm -i -v "$real":/data --entrypoint sh "$IMG" \
        -c "find /data -mindepth 1 -delete && tar xzf - -C /data" < "$BK/$v.tar.gz" || die "Restoring $v failed."
    ok "$v restored"
done

# --- check ----------------------------------------------------------------------------------
info "${C_B}5/5 Starting the backend and checking${C_0}"
dc up -d backend >/dev/null
if wait_health "$HEALTH_URL" 240; then ok "backend answers on $HEALTH_URL"
else dc logs --tail 40 backend || true; die "Restored backend is not healthy."; fi

for t in sessions messages message_translations; do
    n="$(dc exec -T db sh -c "psql -tA -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c 'select count(*) from $t'" | tr -d '\r')"
    want="$(sed -n "s/^rows $t: *//p" "$BK/MANIFEST.txt")"
    if [ -n "$want" ] && [ "$n" != "$want" ]; then warn "rows $t: $n (backup says $want)"; else ok "rows $t: $n"; fi
done
files="$(docker run --rm -v "$(vol_name "$PROJECT" chat_images)":/data:ro --entrypoint sh "$IMG" -c 'find /data -type f | wc -l' | tr -d '\r')"
ok "chat image files: $files"

if [ "$LIVE" = 0 ] && [ "$KEEP_RUNNING" = 0 ]; then
    dc stop >/dev/null
    info "Test copy stopped (its volumes stay). Remove it completely with:"
    info "  docker compose -p $PROJECT --env-file $ENV_FILE down -v"
fi
ok "Restore finished. This backup is proven."
