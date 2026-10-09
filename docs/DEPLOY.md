# Public deployment (read-only)

```
Internet ──► Tailscale Funnel :8443 (only this port; home IP hidden; no router ports opened)
                 │  127.0.0.1:8090
                 ▼
           web     nginx (non-root): static UI + same-origin /api proxy, strict CSP   [edge + internal]
                 │
                 ▼  internal network: no internet, no host, no home LAN
           api     ClearCredit API, read-only, no keys                                 [internal only]
                 │
                 ▼  the API's only way out
           egress  allowlist proxy: CONNECT sepolia.base.org:443, nothing else        [edge + internal]
```

The public API is **read-only**: `CLEARCREDIT_READ_ONLY=1`.

| Area | Behaviour |
|---|---|
| Writes | `POST /claims` and `/claims/{ref}/attest` return `403 READ_ONLY`. |
| Keys | The server **never holds the relayer key**. It uses a random throwaway signer that only performs reads; a real `DEPLOYER_PRIVATE_KEY` is ignored even if set. |
| Satellite evidence | Served from the committed cache only. Public requests never trigger live downloads. |
| Rate limit | Per-client budget, `RATE_LIMIT_PER_MINUTE` (default 120). |
| Containers | All non-root, read-only root filesystems, all capabilities dropped, `no-new-privileges`, memory and PID limits. Only `web` publishes a port, on `127.0.0.1`. |
| Network isolation | `api` is only on a Docker `internal` network, so it has no route to the internet, the host or the LAN. Its one way out is `egress`, which tunnels HTTPS to `sepolia.base.org` and refuses everything else. A compromised API process cannot reach other services on the server or the home network. |
| Browser | Same origin for UI and API (no CORS). Strict CSP: no third-party scripts, no framing; external origins limited to OpenStreetMap tiles and the Base Sepolia RPC. |

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
docker compose -f deploy/docker-compose.yml up -d --build
curl -s http://127.0.0.1:8090/api/health    # {"ok":true,"readOnly":true,"chain":{"chainId":84532,...}}
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

## Optional: frontend on Vercel instead (free Hobby plan)

The `web` container already serves the UI. Vercel is only needed if you want the UI on a separate host.

1. Import the GitHub repo into Vercel and set **Root Directory** to `frontend` (framework: Vite).
2. Environment variables:
   - `VITE_API_URL=https://<host>.ts.net:8443`
   - `VITE_CHAIN_ID=84532`
3. Deploy. `frontend/vercel.json` rewrites all paths to `index.html`, so deep links like `/verify/VCS1115` work.
4. Add the Vercel URL to the backend's `CORS_ORIGINS` and restart the container.
