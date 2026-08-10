# Deploying Pulse

CI builds the images; the Debian host pulls them. Nothing needs to reach in
from the internet, so the box can sit behind NAT with no inbound ports open.

```
push to main ──> GitHub Actions ──> ghcr.io/<owner>/fitnessapp-{api,web}
                                            │
                          Debian host ──────┘  ./deploy.sh
```

## One-time: the repository

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin git@github.com:anton-jj/fitnessAPP.git
git push -u origin main
```

`.env` is gitignored and must stay that way — it holds your API keys.

Nothing else is needed on GitHub's side: the workflow authenticates to the
container registry with the built-in `GITHUB_TOKEN`. The first successful run
on `main` creates both packages.

If the packages are created as private (the default), let the host read them:
create a classic PAT with `read:packages`, then on the Debian box run

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u anton-jj --password-stdin
```

Alternatively make the two packages public under
`github.com/users/anton-jj/packages`, and no login is needed.

## One-time: the Debian host (Proxmox LXC)

These steps assume the `/opt/stacks/<app>/` layout, one directory per stack.

### 1. Allow Tailscale's TUN device (Proxmox host, not the container)

An unprivileged LXC cannot open `/dev/net/tun` by default, so Tailscale will
fail to start until the host passes it through. On the **Proxmox host**, with
the container stopped, add these two lines to `/etc/pve/lxc/<CTID>.conf`:

```
lxc.cgroup2.devices.allow: c 10:200 rwm
lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file
```

Then start the container again. Skip this only if the LXC is privileged or you
intend to run Tailscale in userspace mode.

### 2. Create the stack

```bash
mkdir -p /opt/stacks/pulse && cd /opt/stacks/pulse

curl -O https://raw.githubusercontent.com/anton-jj/fitnessAPP/main/docker-compose.prod.yml
curl -O https://raw.githubusercontent.com/anton-jj/fitnessAPP/main/deploy.sh
curl -o .env https://raw.githubusercontent.com/anton-jj/fitnessAPP/main/.env.example
chmod +x deploy.sh
```

`deploy.sh` picks up whichever compose file is in the directory, so rename it
to `compose.yml` if that matches your other stacks.

### 3. Fill in .env

```bash
nano .env
```

At minimum:

```
IMAGE_OWNER=anton-jj/fitnessapp     # lowercase — GHCR rejects capitals
IMAGE_TAG=latest
WEB_PORT=8080                       # any free port on the LXC
ANTHROPIC_API_KEY=sk-ant-...
INTERVALS_API_KEY=...
INTERVALS_ATHLETE_ID=i123456
```

### 4. Deploy

```bash
./deploy.sh
```

### 5. Join the tailnet

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
sudo tailscale serve --bg 8080
```

## Reference: the Debian host

```bash
mkdir -p /opt/pulse && cd /opt/pulse

# only these three files are needed on the host
curl -O https://raw.githubusercontent.com/anton-jj/fitnessAPP/main/docker-compose.prod.yml
curl -O https://raw.githubusercontent.com/anton-jj/fitnessAPP/main/deploy.sh
curl -o .env https://raw.githubusercontent.com/anton-jj/fitnessAPP/main/.env.example
chmod +x deploy.sh

nano .env    # fill in secrets, and set IMAGE_OWNER / WEB_PORT
./deploy.sh
```

Pulse has no login, so keep it on a private network — see
[Reaching it from your phone](#reaching-it-from-your-phone-tailscale).

`IMAGE_OWNER` must be **lowercase** (`anton-jj/fitnessapp`) — GHCR rejects
capitals even when the repository name has them.

The UI is then on `http://<host>:8080`. The API is not published to the host
at all; nginx inside the `web` container proxies `/api` to it over the private
compose network.

Data lives in the `pulse-data` Docker volume and survives redeploys.

## Updating

```bash
cd /opt/pulse && ./deploy.sh
```

Pulls `latest`, restarts, waits for `/api/health`, and prunes old layers. If
the API does not come up it prints the logs and exits non-zero, leaving the
previous container's data untouched.

To automate it, add a cron entry:

```
*/15 * * * * cd /opt/pulse && ./deploy.sh >> /var/log/pulse-deploy.log 2>&1
```

## Rolling back

Every build is also tagged with its commit sha:

```bash
./deploy.sh sha-<full-commit-sha>
```

Find the sha under the repo's **Packages**, or from the commit history.
To make it stick across future runs, set `IMAGE_TAG=sha-<...>` in `.env`.

## Backups

The SQLite database is the only state:

```bash
docker run --rm -v pulse_pulse-data:/data -v "$PWD:/backup" alpine \
  tar czf /backup/pulse-$(date +%F).tar.gz -C /data .
```

Restore by extracting back into the same volume with the stack stopped.

## Watch sync

See [SYNC.md](SYNC.md). Short version: Pulse writes planned sessions to your
intervals.icu calendar and intervals.icu forwards them to Garmin, COROS,
Wahoo, Polar or Suunto. Direct Garmin and COROS APIs are partner-gated and not
available to a self-hosted app.

## Reaching it from your phone (Tailscale)

Pulse has **no authentication** — every endpoint is open to anything that can
reach it. That is fine on a private network and unacceptable on the open
internet, so do not port-forward it. Tailscale gives your phone a private
route to the box without exposing anything.

**On the Debian host**

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

**On your phone** — install Tailscale from the App Store or Play Store and
sign in with the same account. Both devices are now on your tailnet.

That is already enough: with the stack running, open

```
http://<hostname>:8080
```

from the phone, where `<hostname>` is the machine name Tailscale shows (MagicDNS
resolves it automatically).

**Optional — real HTTPS and a nicer address**

```bash
sudo tailscale serve --bg 8080
```

This publishes it as `https://<hostname>.<your-tailnet>.ts.net` with a valid
certificate, so iOS will let you "Add to Home Screen" and it behaves like an
installed app. Check what is being served with `tailscale serve status`, and
remove it with `tailscale serve --https=443 off`.

> **Never use `tailscale funnel` for this.** Funnel is the sibling command that
> puts a service on the **public internet**. With no auth in front of Pulse,
> that would expose your training history, your settings, and an endpoint that
> spends your Anthropic credits. `serve` keeps it inside your tailnet; `funnel`
> does not.

If you later add authentication, Funnel or a normal reverse proxy becomes a
reasonable option — and remember the 600s proxy timeout either way.

## Plan generation and timeouts

Writing a training block is minutes of model time — roughly 90s for a 4-week
plan and 4-5 minutes for 12 weeks. Two things make that survivable:

- The API starts generation as a **background job** and returns immediately.
  The browser polls `/api/profile/generate-plan/status`, so closing the tab
  or losing the connection does not kill the run.
- nginx is configured with a 600s `proxy_read_timeout` for `/api/`. Its
  default is 60s, which would cut off any long request.

If you put your own reverse proxy (Caddy, Traefik, another nginx) in front of
this stack, give it a matching timeout or plan generation will appear to fail
while the backend is still working.

## What CI checks

| Job | Runs on | Does |
|---|---|---|
| `backend` | every push and PR | imports the app, runs the plan-builder test suite |
| `frontend` | every push and PR | `tsc --noEmit`, production build |
| `images` | `main` only | builds and pushes both images to GHCR |

Pull requests run the checks but publish nothing, so `latest` only ever moves
when `main` is green.
