# Data protection (GDPR / DSGVO) of the AI chatbot

## Where personal data lives

| Data | Where | Deleted by |
|---|---|---|
| Chats: sessions (user id, course, title), messages, translations | Backend PostgreSQL, volume `pg_data` | retention, user request |
| Images attached to messages | Backend volume `chat_images` | retention, user request |
| Course index (no personal data) | Backend volume `chroma_data` | – |
| Message text sent to the language model | Mistral AI (EU), kept up to 30 days for abuse monitoring unless zero data retention is agreed | Mistral |
| Backups | `backups/` and wherever they are copied to | `--keep N`, manual |

Moodle itself stores no chat data any more. Old test chats from before the move may still sit in the
tables `local_ai_system_*` of Moodle's database; the privacy provider removes them when it erases a user.

## Rights of the user (Moodle: Site administration > Users > Privacy and policies > Data requests)

`classes/privacy/provider.php` asks the backend (`/privacy/user/summary`, `/export`, `/delete`, `/users`):

* **Export** returns every chat with messages, translations, timestamps and image file names.
* **Erase** removes rows and image files. If a file cannot be removed the request FAILS and nothing is
  deleted from the database, so it can be repeated. Moodle shows the failed request.
* The endpoints need the HMAC signature and `X-Internal-Api-Key`; they are never reachable for students.

## Retention

`CHAT_RETENTION_DAYS` in `.env.docker` (default **0 = off**). Every night (03:17, Moodle scheduled task
"Delete expired AI chatbot chats", needs working Moodle cron) the backend deletes chats whose last
activity (`sessions.updated_at`) is older. Archived chats are included. The number of removed rows is
written to the backend log (`[privacy] retention ...`). Backups made earlier still contain the old
chats until they are rotated out, which has to be part of the retention decision.

Switching on: set e.g. `CHAT_RETENTION_DAYS=180`, then `docker compose --env-file .env.docker up -d backend`.

## Checks

* Run the task now: Site administration > Server > Tasks > Scheduled tasks > "Delete expired AI chatbot
  chats" > Run now. Result: `local_ai_system cleanup: {...}`.
* Make a data request for a test user (type "export", then "delete"), approve it, and look at the backend log.
