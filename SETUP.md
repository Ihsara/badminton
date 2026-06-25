# Deploying Badminton Bros

Two pieces, by design:

| | What | Where | Visibility |
|---|---|---|---|
| **Home server** | the always-on container — explorer + web editing | your Windows machine | you + LAN (or a tunnel) |
| **Public snapshot** | static explorer on GitHub Pages | `ihsara.github.io/...` | public, sanitized |

The **private data** (real Excel, `players.csv` with nickname→real-name→profile
GUID) lives in a nested git repo at `data/.git` and is **never** pushed to the
public repo. Only the GUID-free `web/data.json` snapshot is published.

---

## 1. The two repos

```
~/badminton/        ← PUBLIC repo (Ihsara). Code + web + sanitized data.json.
  data/             ← PRIVATE repo (data/.git). Gitignored by the public repo.
```

Already initialised locally:
- public repo: commit identity is `Ihsara <ihsara@users.noreply.github.com>`
  (set per-repo so it never uses your Kesko global identity).
- private repo (`data/`): its own history; first commit already made.

### Log in as Ihsara (you are NOT yet)

```bash
gh auth login            # choose the Ihsara account, HTTPS
gh auth switch           # flip between accounts later
```

For full email privacy, replace the placeholder commit email with Ihsara's real
no-reply (GitHub → Settings → Emails → "Keep my email address private"):

```bash
git -C ~/badminton config user.email "<ID>+ihsara@users.noreply.github.com"
```

### Create the remotes

```bash
# PUBLIC (Ihsara) — code + sanitized snapshot
gh repo create ihsara/badminton --public --source ~/badminton --remote origin --push

# PRIVATE — the data. Keep it separate and private.
cd ~/badminton/data
gh repo create ihsara/badminton-data --private --source . --remote origin --push
```

> Double-check before the first public push: `git -C ~/badminton status` must
> NOT list anything under `data/`, `.env`, or `out/`. It won't — they're
> gitignored — but verify once.

---

## 2. Run the home server (Windows)

Install **Docker Desktop**, then in the project folder:

```
copy .env.example .env          REM then set BADMINTON_EDIT_PASSWORD=<something>
windows\start.bat               REM builds + starts at http://localhost:8000
```

**Autostart on boot:**
1. Docker Desktop → Settings → General → "Start Docker Desktop when you log in".
2. `powershell -ExecutionPolicy Bypass -File windows\install-autostart.ps1`

The container has `restart: unless-stopped`, so it comes back after reboots.

No Docker? `windows\run-no-docker.bat` (needs `uv` installed on Windows).

---

## 3. Editing from the browser

Open the server and use the **Maintain** tab (only shows when the container is
reachable and an edit password is set):

- **Replace the match log** — Santeri uploads the `.xlsx`. It is validated in
  Python (real xlsx, no macros, correct `Data` sheet + columns, size limit)
  before anything is saved, then committed to `data/.git` with a readable diff.
- **Nicknames** — anyone edits the name→nickname table; saved + committed.

Every change is one commit in the private repo:

```bash
git -C data log --oneline                 # history
git -C data diff HEAD~1 -- matches_mirror.csv   # readable match-log delta
git -C data revert <hash>                 # undo
```

---

## 4. Publish the public snapshot

The public site shows `web/data.json`. To refresh it for friends:

```
windows\publish.bat        REM regenerates data.json, commits, pushes to Ihsara
```

Then enable Pages once: GitHub repo → Settings → Pages → Source = "GitHub
Actions". The included workflow deploys `web/` on every push that touches it.

---

## 5. Making the home server reachable from the public site (optional)

A GitHub Pages (https) page **cannot** call `http://localhost` (mixed content).
To let the public site pull live data, expose the container over **HTTPS** with a
tunnel — e.g. [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
or Tailscale Funnel — then set in `web/config.js`:

```js
window.BADMINTON_CONFIG = { apiBase: "https://badminton.yourdomain.com" };
```

The site then prefers live data and shows an **"offline, showing snapshot"**
banner when the tunnel is down. Leave `apiBase: ""` for snapshot-only.

---

## Privacy checklist before going public

- [ ] `gh auth status` shows **Ihsara** active (not longchautran/Kesko).
- [ ] Public repo commit author is `Ihsara`, not your Kesko email.
- [ ] `git -C ~/badminton ls-files | grep -E 'data/|\.env'` → empty.
- [ ] `web/data.json` contains no profile GUIDs (it doesn't — verified by build).
