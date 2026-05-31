# Oracle Cloud Always Free Deployment

This path deploys SoundScrapper to a single Ubuntu VM on Oracle Cloud
Infrastructure (OCI). FastAPI serves the backend and static frontend. Nginx
listens on port 80 and proxies to uvicorn on `127.0.0.1:8000`.

Official OCI references:

- [OCI Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- [OCI Free Tier](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm)
- [Connect to a Linux instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/connect-to-linux-instance.htm)
- [OCI security rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm)

## Recommended VM

- Shape: `VM.Standard.A1.Flex` with the Always Free label
- CPU/memory: 1 OCPU and 6 GB RAM is enough for this app
- Image: Ubuntu 24.04 LTS, or Ubuntu 22.04 LTS
- Boot volume: default 50 GB
- Public IP: enabled

OCI Always Free compute instances must be created in the tenancy home region.
If OCI reports out-of-host-capacity for A1, retry another availability domain
or retry later.

## OCI Console Steps

1. Create an Always Free Ubuntu compute instance.
2. Save the generated SSH private key.
3. Add an ingress security rule for HTTP:

```text
Source CIDR: 0.0.0.0/0
IP Protocol: TCP
Destination Port Range: 80
```

4. Keep SSH port 22 open only to your own IP when possible.
5. SSH into the instance. Ubuntu images use the `ubuntu` user:

```powershell
ssh -i C:\path\to\oracle.key ubuntu@<public-ip>
```

## Install On The VM

Run these commands on the Ubuntu VM:

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/nadoman354/SoundScrapper.git
cd SoundScrapper
sudo bash deploy/oracle/setup_ubuntu.sh
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
http://<public-ip>/health
http://<public-ip>/
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
sudo bash deploy/oracle/setup_ubuntu.sh
sudo systemctl restart soundscrapper
```

The script does not overwrite an existing `/opt/soundscrapper/.env`, and it
keeps the database and preview cache under `/var/lib/soundscrapper`.

## Notes And Risks

- This deployment is link-shared, not authenticated. Anyone with the URL can
  search, save candidates, and submit feedback.
- Always Free resources must stay within OCI's free limits. Confirm every
  resource shows the Always Free label before creating it.
- Idle Always Free compute instances may be reclaimed by Oracle.
- Port 80 must be open both in OCI security rules and the VM OS firewall.
- HTTPS is not configured here. Add a domain and Certbot later if public use
  needs TLS.
