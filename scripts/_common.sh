# Shared helpers for deploy.sh / backup.sh / restore.sh (sourced, not run).
# shellcheck shell=bash

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-.env.docker}"
PROJECT="${COMPOSE_PROJECT:-sdg-campus-ai}"     # = "name:" in docker-compose.yml

if [ -t 1 ]; then C_R=$'\e[31m'; C_G=$'\e[32m'; C_Y=$'\e[33m'; C_B=$'\e[1m'; C_0=$'\e[0m'
else C_R=; C_G=; C_Y=; C_B=; C_0=; fi

info() { printf '%s\n' "$*"; }
ok()   { printf '%s✔%s %s\n' "$C_G" "$C_0" "$*"; }
warn() { printf '%s! %s%s\n' "$C_Y" "$*" "$C_0" >&2; }
die()  { printf '%sERROR:%s %s\n' "$C_R" "$C_0" "$*" >&2; exit 1; }

need_cmd() { command -v "$1" >/dev/null 2>&1 || die "'$1' is not installed ($2)."; }

check_docker() {
    need_cmd docker "install Docker Engine, https://docs.docker.com/engine/install/"
    docker compose version >/dev/null 2>&1 || die "'docker compose' (v2 plugin) is missing."
    docker info >/dev/null 2>&1 || die "Cannot talk to the Docker daemon (not running, or no permission: add your user to the 'docker' group)."
}

# docker compose for project $PROJECT. COMPOSE_FILES is e.g. "-f docker-compose.yml -f docker-compose.prod.yml"
COMPOSE_FILES="${COMPOSE_FILES:-}"
dc() {
    # shellcheck disable=SC2086
    docker compose -p "$PROJECT" --env-file "$ENV_FILE" $COMPOSE_FILES "$@"
}

# value of KEY in the env file (last one wins, no quotes handling needed here)
env_get() { sed -n -E "s/^$1=(.*)$/\1/p" "$ROOT/$ENV_FILE" | tail -n1 | tr -d '\r'; }

# real docker name of a compose volume: vol_name <project> <volume>
vol_name() {
    docker volume ls -q \
        --filter "label=com.docker.compose.project=$1" \
        --filter "label=com.docker.compose.volume=$2" | head -n1
}

# Image used for helper containers (tar, gzip, sh) -- the postgres image is already present.
helper_image() { dc config --images 2>/dev/null | grep -m1 '^postgres' || echo postgres:16-alpine; }

# wait_healthy <url> <seconds>
wait_health() {
    local url="$1" max="${2:-180}" i=0
    while [ "$i" -lt "$max" ]; do
        if command -v curl >/dev/null 2>&1; then
            curl -fsS --max-time 3 "$url" >/dev/null 2>&1 && return 0
        else
            dc exec -T backend python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8001/health',timeout=3)" >/dev/null 2>&1 && return 0
        fi
        sleep 3; i=$((i + 3))
    done
    return 1
}
