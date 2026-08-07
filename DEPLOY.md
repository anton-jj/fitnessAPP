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

## One-time: the Debian host

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

## What CI checks

| Job | Runs on | Does |
|---|---|---|
| `backend` | every push and PR | imports the app, runs the plan-builder test suite |
| `frontend` | every push and PR | `tsc --noEmit`, production build |
| `images` | `main` only | builds and pushes both images to GHCR |

Pull requests run the checks but publish nothing, so `latest` only ever moves
when `main` is green.
