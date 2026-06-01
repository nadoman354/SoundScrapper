# DuckDNS Subdomain Setup

DuckDNS is the lightweight free-domain path for friend-only sharing. It gives
you a free subdomain such as:

```text
soundscrapper.duckdns.org
```

Official DuckDNS references:

- [DuckDNS home](https://www.duckdns.org/)
- [DuckDNS Linux cron install](https://www.duckdns.org/install.jsp)

## Create The Subdomain

1. Open DuckDNS and sign in.
2. Create a subdomain, for example `soundscrapper`.
3. Keep the DuckDNS token private. Treat it like a password.

The final app URL will be:

```text
http://soundscrapper.duckdns.org/
http://soundscrapper.duckdns.org/health
```

## Point DuckDNS To The Google VM

Run this on the Google VM over SSH. Replace the placeholders first:

```bash
DUCKDNS_DOMAIN="soundscrapper"
DUCKDNS_TOKEN="your_duckdns_token_here"
curl "https://www.duckdns.org/update?domains=${DUCKDNS_DOMAIN}&token=${DUCKDNS_TOKEN}&ip="
```

Expected response:

```text
OK
```

The blank `ip=` lets DuckDNS detect the Google VM public IP from the request.

Then check:

```bash
curl -s http://127.0.0.1:8000/health
curl -s "http://${DUCKDNS_DOMAIN}.duckdns.org/health"
```

## Keep The IP Updated

Google VM external IPs can change if the VM is stopped and started. To keep
DuckDNS updated, create the updater on the VM:

```bash
mkdir -p ~/duckdns
nano ~/duckdns/duck.sh
```

Paste this, replacing both placeholders:

```bash
#!/usr/bin/env bash
echo url="https://www.duckdns.org/update?domains=soundscrapper&token=your_duckdns_token_here&ip=" | curl -k -o "$HOME/duckdns/duck.log" -K -
```

Save, then enable it:

```bash
chmod 700 ~/duckdns/duck.sh
(crontab -l 2>/dev/null; echo "*/5 * * * * $HOME/duckdns/duck.sh >/dev/null 2>&1") | crontab -
~/duckdns/duck.sh
cat ~/duckdns/duck.log
```

Expected log:

```text
OK
```

## Optional HTTPS

HTTP is enough for a private friend-only demo, but HTTPS is better if the link
will be shared more broadly.

Before running Certbot:

1. Confirm `http://<subdomain>.duckdns.org/` works.
2. Open TCP port 443 in Google Cloud firewall rules.

Then run:

```bash
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d soundscrapper.duckdns.org
sudo certbot renew --dry-run
```

After that, use:

```text
https://soundscrapper.duckdns.org/
```

## Notes

- DuckDNS gives you a borrowed subdomain, not a domain you own.
- Do not publish the DuckDNS token in GitHub, chat, screenshots, or README
  examples.
- The current app is link-shared and has no login. Anyone with the URL can use
  search, save sounds, and submit feedback.
- For long-term public release, use a paid domain and add authentication.
