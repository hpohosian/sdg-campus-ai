#!/usr/bin/env bash
# Backs up everything the backend owns:
#   db.sql.gz           chat database (pg_dump, consistent while running)
#   chat_images.tar.gz  images attached to chat messages
#   chroma_data.tar.gz  ChromaDB index of the course material
#   env.docker          .env.docker (secrets! the backup folder is mode 700)
#   MANIFEST.txt        date, git commit, database revision, row counts
#   SHA256SUMS          checksums, verified again by restore.sh
#
#   scripts/backup.sh                   # -> ./backups/sdg-<date>/ , keeps the newest 14
#   scripts/backup.sh --dir /mnt/backup --keep 30
#   scripts/backup.sh --no-stop         # do not stop the backend for the file copy (see below)
#
# The backend is stopped for a few seconds while the two volumes are copied: ChromaDB is an
# SQLite file that can be torn if it is copied during a write. The database dump needs no stop.
# A backup only counts once scripts/restore.sh has restored it successfully at least once.
# Keep a copy OFF this machine (scp / rsync / the university backup).
set -euo pipefail
# shellcheck source=scripts/_common.sh
. "$(dirname "$0")/_common.sh"
cd "$ROOT"

DIR="$ROOT/backups"; KEEP=14; STOP=1
while [ $# -gt 0 ]; do
    case "$1" in
        --dir) DIR="$(mkdir -p "$2" && cd "$2" && pwd)"; shift ;;
        --keep) KEEP="$2"; shift ;;
        --no-stop) STOP=0 ;;
        -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "Unknown option: $1 (see --help)" ;;
    esac
    shift
done
case "$KEEP" in ''|*[!0-9]*) die "--keep needs a number." ;; esac

check_docker
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found."
[ -n "$(dc ps -q db 2>/dev/null)" ] || die "The database container is not running (nothing to dump). Start it: docker compose --env-file $ENV_FILE up -d db"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$DIR/sdg-$STAMP"
TMP="$OUT"                      # written in place (no rename: Windows drives under WSL dislike renaming folders)
mkdir -p "$DIR"; umask 077; mkdir "$OUT"
DONE=0

IMG="$(helper_image)"
BACKEND_WAS_UP=0
restart_backend() { if [ "$BACKEND_WAS_UP" = 1 ]; then dc start backend >/dev/null && BACKEND_WAS_UP=0; fi; }
trap 'restart_backend; [ "$DONE" = 1 ] || rm -rf "$OUT"' EXIT

# 1. database
info "database ..."
if ! dc exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --no-privileges' \
    | gzip -9 > "$TMP/db.sql.gz"; then
    die "pg_dump failed."
fi
gzip -t "$TMP/db.sql.gz" || die "db.sql.gz is corrupt."
[ "$(gzip -dc "$TMP/db.sql.gz" | wc -c)" -gt 200 ] || die "The dump is suspiciously small."

# 2. volumes
if [ "$STOP" = 1 ] && [ -n "$(dc ps -q --status running backend 2>/dev/null)" ]; then
    info "stopping backend for the file copy ..."
    dc stop backend >/dev/null; BACKEND_WAS_UP=1
fi
for v in chat_images chroma_data; do
    real="$(vol_name "$PROJECT" "$v")"
    if [ -z "$real" ]; then warn "volume $v does not exist yet - skipped"; continue; fi
    info "volume $v ($real) ..."
    # the archive is streamed through stdout: no host folder has to be mounted into the helper container
    if ! docker run --rm -v "$real":/data:ro --entrypoint tar "$IMG" czf - -C /data . > "$OUT/$v.tar.gz"; then
        die "tar of $v failed."
    fi
    gzip -t "$OUT/$v.tar.gz" || die "$v.tar.gz is corrupt."
done
restart_backend

# 3. config + manifest
cp "$ROOT/$ENV_FILE" "$TMP/env.docker"
{
    echo "created:     $(date -Is)"
    echo "host:        $(hostname)"
    echo "project:     $PROJECT"
    echo "git commit:  $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo n/a)$(git -C "$ROOT" diff --quiet 2>/dev/null || echo ' (+uncommitted changes)')"
    echo "db revision: $(dc exec -T db sh -c 'psql -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select version_num from alembic_version"' 2>/dev/null | tr -d '\r' || echo n/a)"
    for t in sessions messages message_translations; do
        echo "rows $t: $(dc exec -T db sh -c "psql -tA -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c 'select count(*) from $t'" 2>/dev/null | tr -d '\r' || echo n/a)"
    done
} > "$TMP/MANIFEST.txt"
( cd "$TMP" && sha256sum db.sql.gz env.docker MANIFEST.txt $(ls ./*.tar.gz 2>/dev/null) > SHA256SUMS )
( cd "$TMP" && sha256sum -c SHA256SUMS >/dev/null ) || die "checksum self-test failed."

chmod -R go-rwx "$OUT" 2>/dev/null || true
DONE=1
ok "backup written: $OUT ($(du -sh "$OUT" | cut -f1))"
cat "$OUT/MANIFEST.txt" | sed 's/^/    /'

# 4. retention
mapfile -t old < <(ls -1d "$DIR"/sdg-* 2>/dev/null | sort | head -n "-$KEEP" 2>/dev/null || true)
for d in "${old[@]:-}"; do [ -n "$d" ] && [ -d "$d" ] && { rm -rf "$d"; info "removed old backup $(basename "$d")"; }; done
info "Reminder: copy backups off this machine, and test them once with scripts/restore.sh."
