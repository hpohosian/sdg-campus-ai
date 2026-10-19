# Security of the plugin -> backend connection

The browser never talks to the backend. The student's browser talks to Moodle (PHP),
and the Moodle plugin calls the backend server-to-server. The measures below protect that
connection.

| Measure | How it works here | Where |
|---|---|---|
| Authentication | Every request carries an HMAC-SHA256 signature over timestamp, method, path, user id, enrolled courses and body. The shared secret itself never travels. Replay window 300 s. Missing or wrong signature: 401. | `api/middleware/auth.py`, `moodle-plugin/.../request_signer.php` |
| Health check | `GET /health` (unsigned) runs `SELECT 1` on the chat database, 503 if it fails. Used as Docker healthcheck. | `api/main.py` |
| Rate limit | Per Moodle user and minute: `RATE_LIMIT_PER_MIN` (default 120) and, for everything that makes the model answer, `RATE_LIMIT_LLM_PER_MIN` (default 12). 429 with `Retry-After`. 0 switches a limit off. | `api/middleware/rate_limit.py` |
| CORS | None. The browser has no reason to call the backend, so no origin is allowed. | `api/main.py` |
| Security headers | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`; HSTS when the request came in over HTTPS. | `api/middleware/security_headers.py`, `deploy/nginx.conf.template` |
| Secrets | `scripts/generate-secrets.ps1` / `.sh` create `.env.docker` with random values (mode 600 on Linux). `.env.docker` and `deploy/certs/` are in `.gitignore`. | `scripts/` |
| Docs off in production | `ENVIRONMENT=production` removes `/docs`, `/redoc`, `/openapi.json`. | `api/main.py` |
| Internal endpoints | `/rag/index*` additionally need `X-Internal-Api-Key`. | `verify_internal_api_key` (internal_auth.py) |

## Streaming (SSE) behind a reverse proxy

Chat answers are Server-Sent Events. A proxy that buffers makes them look "hung".
`deploy/nginx.conf.template` therefore sets `proxy_buffering off`, one-hour timeouts and
HTTP/1.1; the backend also sends `X-Accel-Buffering: no` on every event stream. The same
applies to any other proxy in front of **Moodle** (the browser's chat request goes through
it too): no response buffering and long timeouts.

## HTTPS in front of the backend (optional)

Only needed when something outside the docker network must reach the backend, e.g. Moodle on a
different server. See the header of `docker-compose.prod.yml`. If Moodle and the backend share a
host or docker network, the plugin can call the backend directly and the nginx layer is not needed.

## Checks

```bash
curl -i http://127.0.0.1:8001/health               # 200, security headers present
curl -i http://127.0.0.1:8001/sessions             # 401 (unsigned)
curl -i https://<host>/health                      # via nginx: 200, HSTS exactly once
php local/ai_system/cli/ping_backend.php 2         # signed request from Moodle: 200
```
Rate limit: send more than `RATE_LIMIT_LLM_PER_MIN` chat messages in one minute with the same
user; the extra ones get 429 (and `[rate-limit]` appears in the backend log).
