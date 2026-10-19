# Deploying and backing up the backend (Linux VM)

All commands run from the repository root. Needs Docker Engine with the compose plugin.

## First install

```bash
git clone <repo> && cd <repo>
# optional HTTPS: put fullchain.pem / privkey.pem into deploy/certs/ (see docker-compose.prod.yml)
scripts/deploy.sh            # or: scripts/deploy.sh --prod
```

`deploy.sh` checks Docker, creates `.env.docker` with random secrets (mode 600), asks for the
Mistral API key (hidden), builds and starts everything, waits for `/health` and prints what to enter
in the Moodle plugin settings (`api_base_url`, `api_secret`, `internal_api_key`). Then, on the Moodle
machine, `php local/ai_system/cli/ping_backend.php <userid>` must answer HTTP 200.

Before the first real use edit `.env.docker`: `ENVIRONMENT=production`, `DEBUG=false`,
the real `DATABASE_URL` and `MOODLEDATA_HOST_PATH` (until stage 2.3 is done).

## Update

```bash
git pull
scripts/deploy.sh            # backs up first, rebuilds, restarts, checks /health
```
Safe to repeat: secrets, database, images and index are kept. The database schema is migrated
automatically at container start (`alembic upgrade head`).

## Backups

```bash
scripts/backup.sh                       # ./backups/sdg-<date>/, keeps the newest 14
scripts/backup.sh --dir /mnt/backup --keep 30
```
Contains the chat database (`pg_dump`), chat images, ChromaDB index, `.env.docker` (secrets: the
folder is mode 700) and checksums. The backend is stopped for a few seconds during the file copy.
Daily at 03:15 with cron (`crontab -e`):
```
15 3 * * * cd /opt/sdg-campus-ai && scripts/backup.sh --dir /var/backups/sdg --keep 30 >> /var/log/sdg-backup.log 2>&1
```
**Copy backups off the machine** (rsync / scp / university backup). A backup on the same disk does
not survive a lost VM.

## Restore – and proving that a backup works

```bash
scripts/restore.sh backups/sdg-20261019-030000          # test copy, live system untouched
```
Builds a separate project `sdg-campus-restore` (own volumes, database on 127.0.0.1:25432, backend on
127.0.0.1:18001), loads the backup, checks `/health` and the row counts against the backup's
`MANIFEST.txt`. Do this once after setting up backups and then every few months. Remove the test copy:
`docker compose -p sdg-campus-restore --env-file .env.docker down -v` (only that project name!).

Real restore (new VM or rollback): clone the repo, then
```bash
scripts/restore.sh <backup> --project sdg-campus-ai     # asks you to type the project name
```
On a fresh VM it installs `.env.docker` from the backup. Afterwards the Moodle settings are unchanged,
because `MOODLE_SECRET` is restored too.

## Rules

* **Never `docker compose down -v`** on the live project – it deletes the volumes (chat database,
  images, index). `down` (without `-v`) and `restart` are fine.
* The data lives in the volumes `pg_data`, `chat_images`, `chroma_data`, not in the containers.
* Add `backups/` to `.gitignore`; keep `*.sh` with LF line endings (`.gitattributes`: `*.sh text eol=lf`).
* The scripts are for Linux (bash). On Windows run them in WSL, or use the plain `docker compose`
  commands from the header of `docker-compose.yml`.
