# Public deployment (read-only)

```
browser ──► Vercel (static frontend)  ──VITE_API_URL──►  https://<host>.ts.net:8443  (Tailscale Funnel)
                                                              │
                                                              ▼  127.0.0.1:8090
                                                 Docker: ClearCredit API, read-only
                                                              │  reads
                                                              ▼
                                         Base Sepolia contract 0x889BD5e5462139D7AA8384d520f00403De8CB2b4
```

The public API is **read-only**: `CLEARCREDIT_READ_ONLY=1`.

| Area | Behaviour |
|---|---|
| Writes | `POST /claims` and `/claims/{ref}/attest` return `403 READ_ONLY`. |
| Keys | The server **never holds the relayer key**. It uses a random throwaway signer that only performs reads; a real `DEPLOYER_PRIVATE_KEY` is ignored even if set. |
| Satellite evidence | Served from the committed cache only. Public requests never trigger live downloads. |
| Rate limit | Per-client budget, `RATE_LIMIT_PER_MINUTE` (default 120). |
| Container | Non-root user, read-only root filesystem, all capabilities dropped, `no-new-privileges`, 1 GB memory limit. It listens only on `127.0.0.1`. |

Live registration (signing, relaying, issuing, retiring) is demonstrated locally (`scripts/demo.py`) and in the video. A public writer would hold a funded key that anyone could spend.

## Backend on a home server (Docker + Tailscale Funnel)

**One-time setup** (needs sudo once):

```bash
sudo usermod -aG docker "$USER"        # run Docker without sudo (log out/in after)
sudo tailscale set --operator="$USER"  # manage serve/funnel without sudo
```

**Deploy:**

```bash
git clone <repo> clearcredit && cd clearcredit
mkdir -p deploy/state
cp <registry snapshot>.sqlite3 deploy/state/clearcredit.sqlite3   # optional: pre-seeded registry
CORS_ORIGINS=https://<your-app>.vercel.app docker compose -f deploy/docker-compose.yml up -d --build
curl -s http://127.0.0.1:8090/health        # {"ok":true,"readOnly":true,"chain":{"chainId":84532,...}}
```

**Publish it with Funnel** on its own port, so any existing `tailscale serve` site stays private:

```bash
tailscale funnel --bg --https=8443 http://127.0.0.1:8090
tailscale funnel status
```

Funnel only allows ports 443, 8443 and 10000. Using 8443 leaves anything already served on 443 untouched. The first use may print a link to approve Funnel for the machine in the Tailscale admin console.

To stop publishing:

```bash
tailscale funnel --https=8443 off
docker compose -f deploy/docker-compose.yml down
```

## Frontend on Vercel (free Hobby plan)

1. Import the GitHub repo into Vercel and set **Root Directory** to `frontend` (framework: Vite).
2. Environment variables:
   - `VITE_API_URL=https://<host>.ts.net:8443`
   - `VITE_CHAIN_ID=84532`
3. Deploy. `frontend/vercel.json` rewrites all paths to `index.html`, so deep links like `/verify/VCS1115` work.
4. Add the Vercel URL to the backend's `CORS_ORIGINS` and restart the container.
