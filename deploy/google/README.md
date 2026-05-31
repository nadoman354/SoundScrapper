# Google Cloud Compute Engine Deployment

This path deploys SoundScrapper to a single Ubuntu VM on Google Cloud Compute
Engine. FastAPI serves the backend and static frontend. Nginx listens on port 80
and proxies to uvicorn on `127.0.0.1:8000`.

Official Google Cloud references:

- [Google Cloud Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features)
- [Connect to Linux VMs](https://docs.cloud.google.com/compute/docs/connect/standard-ssh)
- [VPC firewall rules](https://docs.cloud.google.com/firewall/docs/firewalls)
- [Create budgets and alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets)

## Recommended Free Tier VM

- Product: Compute Engine VM instance
- Machine type: `e2-micro`
- Region: `us-west1`, `us-central1`, or `us-east1`
- Boot disk: Standard persistent disk, 30 GB or less
- Image: Ubuntu 24.04 LTS, or Ubuntu 22.04 LTS
- Public IPv4: enabled
- Network tag: `http-server`

Keep total eligible standard persistent disk usage at or below 30 GB-months and
avoid heavy preview-audio traffic. Google Cloud's Compute Engine Free Tier has a
small outbound data allowance.

## Cost Controls

Before exposing the app, create a budget alert in Google Cloud Billing:

1. Open Billing.
2. Open Budgets & alerts.
3. Create a monthly budget for the project.
4. Add alerts at 50%, 90%, and 100%.

The app itself does not use OpenAI or GPT APIs. The main cost risk is VM, disk,
or outbound network usage outside the Free Tier limits.

## Create The VM

Recommended console settings:

1. Create a Compute Engine VM instance.
2. Select one Free Tier region: `us-west1`, `us-central1`, or `us-east1`.
3. Select machine type `e2-micro`.
4. Select Ubuntu 24.04 LTS or Ubuntu 22.04 LTS.
5. Set boot disk type to Standard persistent disk.
6. Keep boot disk size at 30 GB or less.
7. Allow HTTP traffic, or add the `http-server` network tag.
8. Create the VM.

If you use `gcloud`, a firewall rule for port 80 can look like this:

```bash
gcloud compute firewall-rules create allow-soundscrapper-http \
  --direction=INGRESS \
  --priority=1000 \
  --network=default \
  --action=ALLOW \
  --rules=tcp:80 \
  --source-ranges=0.0.0.0/0 \
  --target-tags=http-server
```

## Install On The VM

Connect from the Google Cloud Console SSH button, or use:

```bash
gcloud compute ssh <vm-name> --zone <zone>
```

Run these commands on the Ubuntu VM:

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/nadoman354/SoundScrapper.git
cd SoundScrapper
sudo bash deploy/google/setup_ubuntu.sh
```

Add the Freesound API key:

```bash
sudo nano /opt/soundscrapper/.env
sudo systemctl restart soundscrapper
```

Check the local service:

```bash
curl http://127.0.0.1:8000/health
sudo systemctl status soundscrapper --no-pager
sudo journalctl -u soundscrapper -n 80 --no-pager
```

Check the public URL:

```text
http://<external-ip>/health
http://<external-ip>/
```

## Production Paths

The setup script installs these paths:

```text
/opt/soundscrapper/app       application files
/opt/soundscrapper/.env      server environment file
/var/lib/soundscrapper       persistent SQLite DB and preview cache
```

The service uses:

```text
SOUNDSCRAPPER_DB_PATH=/var/lib/soundscrapper/sound_scout.db
SOUNDSCRAPPER_PREVIEW_CACHE_DIR=/var/lib/soundscrapper/previews
FREESOUND_BASE_URL=https://freesound.org
```

## Update Deployment

Pull the latest code and rerun the setup script:

```bash
cd ~/SoundScrapper
git pull
sudo bash deploy/google/setup_ubuntu.sh
sudo systemctl restart soundscrapper
```

The script does not overwrite an existing `/opt/soundscrapper/.env`, and it
keeps the database and preview cache under `/var/lib/soundscrapper`.

## Notes And Risks

- This deployment is link-shared, not authenticated. Anyone with the URL can
  search, save candidates, and submit feedback.
- Free Tier eligibility depends on the exact region, machine type, disk type,
  disk size, and outbound transfer usage.
- Use Standard persistent disk for the Free Tier disk allowance. Balanced SSD or
  larger disks can create charges.
- HTTPS is not configured here. Add a domain and Certbot later if public use
  needs TLS.
