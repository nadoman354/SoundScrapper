# SoundScrapper

SoundScrapper is a Sound Scout MVP for finding game-ready sound candidates from
Freesound, Jamendo, and Openverse. It provides prompt-based search, preview playback, waveform
inspection, license/duration filtering, saved candidates, audio analysis metrics,
and lightweight user feedback learning backed by SQLite.

## Stack

- Backend: FastAPI
- Frontend: HTML, CSS, vanilla JavaScript
- Database: SQLite
- Source APIs: Freesound APIv2, Jamendo API, Openverse API

## Setup

1. Create a Python environment.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

2. Create `.env` from `.env.example`.

```powershell
Copy-Item .env.example .env
```

3. Add source API keys.

```text
FREESOUND_API_KEY=your_api_key_here
JAMENDO_CLIENT_ID=your_jamendo_client_id_here
OPENVERSE_CLIENT_ID=optional_openverse_client_id
OPENVERSE_CLIENT_SECRET=optional_openverse_client_secret
SOUNDSCRAPPER_DB_PATH=sound_scout.db
SOUNDSCRAPPER_PREVIEW_CACHE_DIR=.cache/previews
FREESOUND_BASE_URL=https://freesound.org
JAMENDO_BASE_URL=https://api.jamendo.com/v3.0
OPENVERSE_BASE_URL=https://api.openverse.org/v1
```

Openverse can run without credentials when anonymous API access is available.
Freesound and Jamendo are skipped with a UI warning when their keys are missing.
Jamendo is best treated as a non-commercial/educational integration unless you
have confirmed your usage terms with Jamendo.

4. Run the server.

```powershell
uvicorn backend.app.main:app --reload
```

5. Open the local app.

```text
http://127.0.0.1:8000/
```

## Verification

Run static analysis before tests after code changes.

```powershell
python -m compileall backend scripts
python -m ruff check .
python -m pytest
```

## Google Cloud Free Tier Deployment

The preferred low-cost deployment path is a Google Cloud Compute Engine
`e2-micro` Ubuntu VM. This repo includes deployment files in `deploy/google/`.

Use this when you want persistent SQLite data and a service that can remain
online without a paid app-hosting plan:

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/nadoman354/SoundScrapper.git
cd SoundScrapper
sudo bash deploy/google/setup_ubuntu.sh
sudo nano /opt/soundscrapper/.env
sudo systemctl restart soundscrapper
```

Recommended Google Cloud Free Tier settings:

```text
Machine type: e2-micro
Region: us-west1, us-central1, or us-east1
Boot disk: Standard persistent disk, 30 GB or less
Network: allow HTTP traffic on port 80
```

The Google deployment uses these production paths:

```text
SOUNDSCRAPPER_DB_PATH=/var/lib/soundscrapper/sound_scout.db
SOUNDSCRAPPER_PREVIEW_CACHE_DIR=/var/lib/soundscrapper/previews
```

Check the deployed app:

```text
http://<external-ip>/health
http://<external-ip>/
```

Set a Google Cloud budget alert before sharing the link. See
`deploy/google/README.md` for the full VM setup, firewall command, update
commands, and cost risks.

## DuckDNS Free Subdomain

For friend-only sharing, use a free DuckDNS subdomain after the Google VM is
working:

```text
http://soundscrapper.duckdns.org/
```

Create the DuckDNS subdomain, then point it to the Google VM public IP with the
DuckDNS update URL from the VM. See `deploy/duckdns/README.md` for the exact
commands, optional cron updater, and optional HTTPS setup.

## Oracle Always Free Deployment

The Oracle Cloud Infrastructure (OCI) Always Free Ubuntu VM path remains
available as an alternative. This repo includes Ubuntu deployment files in
`deploy/oracle/`.

Use this when you want persistent SQLite data without paying for a Render disk:

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/nadoman354/SoundScrapper.git
cd SoundScrapper
sudo bash deploy/oracle/setup_ubuntu.sh
sudo nano /opt/soundscrapper/.env
sudo systemctl restart soundscrapper
```

The Oracle deployment uses these production paths:

```text
SOUNDSCRAPPER_DB_PATH=/var/lib/soundscrapper/sound_scout.db
SOUNDSCRAPPER_PREVIEW_CACHE_DIR=/var/lib/soundscrapper/previews
```

Open port 80 in the OCI security rules, then check:

```text
http://<public-ip>/health
http://<public-ip>/
```

See `deploy/oracle/README.md` for the VM shape, OCI Console steps, update
commands, and risks. The deployed app is link-shared, not authenticated.

## Render Deployment

This repo includes a Render Blueprint in `render.yaml`. It deploys the FastAPI
backend and the static frontend as a single Render Web Service. This is now the
paid managed-hosting alternative because the persistent disk requires a paid
Render service.

1. Push this repo to GitHub.
2. In Render, create a new Blueprint or Web Service from the GitHub repo.
3. Use the settings from `render.yaml`.
4. In the Render dashboard, set `FREESOUND_API_KEY` manually.
5. Confirm the persistent disk is mounted at `/data`.
6. Open the deployed URL and check `/health`.

Render uses these production paths:

```text
SOUNDSCRAPPER_DB_PATH=/data/sound_scout.db
SOUNDSCRAPPER_PREVIEW_CACHE_DIR=/data/previews
```

The server starts with:

```bash
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```

The deployed app is link-shared, not authenticated. Anyone with the URL can use
search, save candidates, and submit feedback. Keep the URL private if the
feedback data should remain personal.

The local `sound_scout.db` is not deployed. The Render service starts with a new
SQLite database on the persistent disk, then keeps saved sounds, analyses,
feedback, and preview cache across restarts and redeploys.

## MVP Scope

Included:

- `GET /health`
- `POST /api/search`
- `POST /api/saved-sounds`
- `GET /api/saved-sounds`
- `GET /api/preview-audio/{sound_id}`
- `POST /api/preview-cache/{sound_id}`
- `POST /api/sound-analyses`
- `GET /api/sound-analyses/{sound_id}`
- `POST /api/feedback`
- Freesound, Jamendo, and Openverse search with source deduplication
- SQLite saved candidates, analysis metrics, and feedback
- Waveform inspection from result cards
- Lightweight feedback-based score adjustment
- Static frontend served by FastAPI

Not included yet:

- Unity project integration
- YouTube search or download
- React or Electron packaging
- Heavy AI or embedding reranking
- Authentication

## License Notes

SoundScrapper displays source, creator, license, and attribution hints, but it
does not guarantee legal clearance. Check each original source page before using
or distributing a sound. CC0 is the safest default; attribution, non-commercial,
no-derivatives, and share-alike licenses need extra review for games.
