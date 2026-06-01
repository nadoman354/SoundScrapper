# Decision Log

## 2026-05-31

### Use Python FastAPI as backend
Reason:
- Python is a good fit for later audio analysis.
- FastAPI gives simple local HTTP APIs for the frontend.
- The MVP can remain lightweight while still hiding API credentials server-side.

### Use HTML/CSS/Vanilla JS first
Reason:
- The MVP does not need React yet.
- Static files keep setup and iteration simple.
- A later React migration can happen after workflows stabilize.

### Use SQLite for saved candidates
Reason:
- The tool is local-first.
- SQLite is enough for saved sounds and search history.
- It avoids adding a database service during the MVP.

### Start with Freesound API
Reason:
- Freesound has an official API.
- It provides metadata, tags, licenses, preview URLs, and analysis descriptors.
- Token authentication is enough for read-only search.

### Do not implement YouTube download
Reason:
- Downloading or analyzing YouTube audio has legal and Terms of Service risk.
- YouTube can be revisited later as a candidate link helper only.

## 2026-06-01

### Use Oracle Cloud Always Free for the first public deployment
Reason:
- The app needs persistent SQLite data and preview cache, but not managed app
  hosting features yet.
- An OCI Ubuntu VM can keep the database and cache on the boot volume without a
  paid persistent disk.
- The deployment remains link-shared without authentication, matching the
  current project scope.

### Prefer Google Cloud Compute Engine for the active deployment path
Reason:
- Google Cloud is easier to access than Oracle Cloud for this project context.
- Compute Engine Free Tier can run an `e2-micro` VM with a standard persistent
  disk, which fits the current FastAPI + SQLite architecture.
- Budget alerts and the Google Cloud console reduce operational risk compared
  with troubleshooting Oracle capacity and account constraints.

### Use DuckDNS for friend-only sharing
Reason:
- The deployed Google VM already works through its public IP, so a free
  subdomain is enough for private sharing.
- DuckDNS avoids paid domain registration while giving a readable URL.
- This remains a link-shared deployment, not an authenticated public product.
