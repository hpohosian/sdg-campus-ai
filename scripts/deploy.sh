#!/usr/bin/env bash
# Installs or updates the SDG Campus AI backend on a Linux VM. Safe to run again:
# existing secrets, database, chat images and ChromaDB index are never touched.
#
#   scripts/deploy.sh                 # first install or update (plain HTTP on 127.0.0.1:8001)
#   scripts/deploy.sh --prod          # + nginx with HTTPS (needs deploy/certs/, see docker-compose.prod.yml)
#   scripts/deploy.sh --no-build      # restart without rebuilding the image
#   scripts/deploy.sh --no-backup     # skip the automatic backup before an update
#   scripts/deploy.sh --show-secrets  # print api_secret / internal_api_key for the Moodle settings
#
# What it does: checks the prerequisites -> creates .env.docker with random secrets (first run
# only) -> asks for the Mistral API key (hidden input) -> backup of the running system ->
# build + start -> waits for /health -> tells you what to enter in Moodle.
set -euo pipefail
# shellcheck source=scripts/_common.sh
. "$(dirname "$0")/_common.sh"
cd "$ROOT"

PROD=0; BUILD=1; BACKUP=1; SHOW=0
for a in "$@"; do
    case "$a" in
        --prod) PROD=1 ;;
        --no-build) BUILD=0 ;;
        --no-backup) BACKUP=0 ;;
        --show-secrets) SHOW=1 ;;
        -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "Unknown option: $a (see --help)" ;;
    esac
done

# --- 1. prerequisites ---------------------------------------------------------
info "${C_B}1/5 Checking prerequisites${C_0}"
check_docker
ok "docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?'), $(docker compose version --short 2>/dev/null)"
[ -f docker-compose.yml ] && [ -f Dockerfile ] || die "Run this from the repository (docker-compose.yml / Dockerfile not found)."

# --- 2. secrets -----------------------------------------------------------------
info "${C_B}2/5 Configuration${C_0}"
FIRST_RUN=0
if [ ! -f "$ENV_FILE" ]; then
    FIRST_RUN=1
    bash scripts/generate-secrets.sh >/dev/null
    ok "created $ENV_FILE with random secrets (mode 600)"
else
    ok "$ENV_FILE exists, secrets are kept"
fi

set_env() {     # set_env KEY VALUE  (value must not contain | or newline)
    local tmp; tmp="$(mktemp)"
    umask 077
    if grep -q "^$1=" "$ENV_FILE"; then sed -E "s|^$1=.*|$1=$2|" "$ENV_FILE" > "$tmp"
    else { cat "$ENV_FILE"; echo "$1=$2"; } > "$tmp"; fi
    cat "$tmp" > "$ENV_FILE"; rm -f "$tmp"
}

key="$(env_get MISTRAL_API_KEY)"
if [ -z "$key" ] || [ "$key" = "xxx" ]; then
    [ -t 0 ] || die "MISTRAL_API_KEY is not set in $ENV_FILE and there is no terminal to ask for it."
    read -r -s -p "Mistral API key (input hidden): " key; echo
    [ -n "$key" ] || die "No key entered."
    set_env MISTRAL_API_KEY "$key"
    ok "MISTRAL_API_KEY saved"
fi

# values that must be filled in by hand (they depend on the machine)
md="$(env_get MOODLEDATA_HOST_PATH)"
if [ -z "$md" ] || [ ! -d "$md" ]; then
    warn "MOODLEDATA_HOST_PATH='$md' is not a directory on this machine."
    warn "The backend still reads course PDFs from Moodle's moodledata (stage 2.3). Fix it in $ENV_FILE."
    [ -t 0 ] || die "Cannot continue without it."
    read -r -p "Path to moodledata on THIS machine: " md
    [ -d "$md" ] || die "'$md' is not a directory."
    set_env MOODLEDATA_HOST_PATH "$md"
fi
case "$(env_get DATABASE_URL)" in *:xxx@*) warn "DATABASE_URL in $ENV_FILE still contains the placeholder password (Moodle's DB: course texts)." ;; esac
if [ "$(env_get ENVIRONMENT)" != "production" ]; then
    warn "ENVIRONMENT is not 'production' (API docs /docs stay on, DEBUG may be on). Set ENVIRONMENT=production and DEBUG=false on the VM."
fi

if [ "$(env_get ENVIRONMENT)" = "production" ] && [ "$(env_get CHAT_RETENTION_DAYS)" = "0" -o -z "$(env_get CHAT_RETENTION_DAYS)" ]; then
    warn "CHAT_RETENTION_DAYS is 0: chats are kept forever. Agree on a retention period (docs/privacy.md)."
fi

if [ "$PROD" = 1 ]; then
    COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml"
    [ -f deploy/certs/fullchain.pem ] && [ -f deploy/certs/privkey.pem ] \
        || die "--prod needs deploy/certs/fullchain.pem and privkey.pem."
    name="$(env_get NGINX_SERVER_NAME)"
    { [ -n "$name" ] && [ "$name" != "backend.example.org" ]; } || die "Set NGINX_SERVER_NAME in $ENV_FILE to the host name of the certificate."
    ok "HTTPS mode: https://$name"
fi
dc config -q || die "docker compose configuration is invalid (see above)."

# --- 3. backup before touching a running system -------------------------------------
info "${C_B}3/5 Backup${C_0}"
if [ "$BACKUP" = 1 ] && [ -n "$(vol_name "$PROJECT" pg_data)" ] && [ -n "$(dc ps -q db 2>/dev/null)" ]; then
    COMPOSE_FILES="$COMPOSE_FILES" bash scripts/backup.sh --keep 14 || die "Backup failed - not updating. (--no-backup skips it.)"
else
    info "nothing to back up yet (first install) or skipped"
fi

# --- 4. build + start ------------------------------------------------------------------
info "${C_B}4/5 Build and start${C_0}"
if [ "$BUILD" = 1 ]; then dc up -d --build; else dc up -d; fi
ok "containers started"

# --- 5. health ----------------------------------------------------------------------------
info "${C_B}5/5 Waiting for /health (the first start loads the embedding model, up to 3 minutes)${C_0}"
if wait_health "http://127.0.0.1:8001/health" 240; then
    ok "backend is healthy"
else
    dc ps
    dc logs --tail 40 backend || true
    die "backend did not become healthy. Logs above; more: docker compose -p $PROJECT --env-file $ENV_FILE logs backend"
fi
if [ "$PROD" = 1 ] && command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 10 "https://$(env_get NGINX_SERVER_NAME)/health" >/dev/null \
        && ok "https://$(env_get NGINX_SERVER_NAME)/health answers" \
        || warn "HTTPS check failed (DNS / firewall / certificate?). docker compose logs nginx"
fi

echo
if [ "$PROD" = 1 ]; then URL="https://$(env_get NGINX_SERVER_NAME)"; else URL="http://127.0.0.1:8001"; fi
info "${C_B}Moodle plugin settings${C_0} (Site administration > Plugins > Local plugins > AI System):"
info "  api_base_url     = $URL   (if Moodle runs on ANOTHER machine, use the backend's HTTPS address)"
if [ "$SHOW" = 1 ] || [ "$FIRST_RUN" = 1 ]; then
    info "  api_secret       = $(env_get MOODLE_SECRET)"
    info "  internal_api_key = $(env_get INTERNAL_API_KEY)"
else
    info "  api_secret       = MOODLE_SECRET from $ENV_FILE        (--show-secrets prints it)"
    info "  internal_api_key = INTERNAL_API_KEY from $ENV_FILE"
fi
info "Then, on the Moodle machine:  php local/ai_system/cli/ping_backend.php <userid>   -> HTTP 200"
echo
info "Never run 'docker compose down -v' - it deletes the chat database, images and the index."
