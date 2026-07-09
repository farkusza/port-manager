# GitHub publish playbook — `ports-registry`

A copy-paste walkthrough for getting the repo onto GitHub.
Do these steps in order. Each section ends with a verification you should run before moving on.

---

## 0. Pre-flight

### 0.1 Token check

A GitHub PAT is already configured at `~/AppData/Local/hermes/.env` (line ~496, `GITHUB_TOKEN=ghp_...`). It has the scopes needed for repo creation, push, and workflow dispatch.

Verify before relying on it:

```bash
curl -s -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d['login'], '—', d.get('name','?'))"
```

Expected: prints your GitHub username.

If the token is missing, expired, or scope-insufficient, generate a new one:

1. Open **https://github.com/settings/tokens**
2. Click **Generate new token → Generate new token (classic)**
3. Scopes — tick **only** these: `repo`, `workflow`
4. Copy the token, then add it to `~/AppData/Local/hermes/.env` as `GITHUB_TOKEN=ghp_...`

### 0.2 Wire the token into git

```bash
cd "C:/Users/farku/Projects/ports-registry"

# Option A — credential helper (recommended)
# Token gets prompted for on first push, then cached to disk.
git config --global credential.helper store

# Option B — embed in remote URL (skip the prompt)
# Use this if you'd rather not cache credentials in plaintext on disk.
git remote add origin https://farkusza:$GITHUB_TOKEN@github.com/farkusza/ports-registry.git
```

**Recommendation:** Option A if the token is reusable across repos and you trust disk caching. Option B is cleaner for a one-off publish.

---

## 1. Create the GitHub repo

Two ways. The `gh` way is one command. The curl way works without `gh`.

### 1a. With `gh` CLI (if installed)

```bash
# Install once: winget install GitHub.cli
gh auth login                       # follow prompts
gh repo create farkusza/ports-registry \
    --public \
    --description "Local port bookkeeping for Windows + WSL developers — no daemon, no OS locks, just a SQLite registry + live scanner." \
    --source . \
    --remote origin
```

### 1b. Without `gh` (curl + token)

```bash
# Set this in your shell once
export GITHUB_TOKEN="<paste-token-here>"

curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/user/repos \
  -d '{
    "name": "ports-registry",
    "description": "Local port bookkeeping for Windows + WSL developers — no daemon, no OS locks, just a SQLite registry + live scanner.",
    "private": false,
    "has_issues": true,
    "has_projects": true,
    "has_wiki": false
  }'
```

**Verify:**
```bash
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/farkusza/ports-registry \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d['full_name'], '—', d['html_url'])"
```
Expected: `farkusza/ports-registry — https://github.com/farkusza/ports-registry`

---

## 2. Commit + push

```bash
cd "C:/Users/farku/Projects/ports-registry"

# Confirm working tree is clean (you've only got untracked publish artifacts right now)
git status

# Stage everything
git add pyproject.toml README.md CHANGELOG.md .gitignore \
        ports.spec .github/

# Commit
git commit -m "build: publish artifacts — pyproject, README, CI, PyInstaller spec

- pyproject.toml: setuptools, ports = ports:main entry point
- README.md: public-facing with install + examples
- CHANGELOG.md: 0.1.0 release notes
- .gitignore: add build/, dist/, .venv/
- ports.spec: PyInstaller single-file Windows .exe
- .github/workflows/ci.yml: test matrix, .exe build, PyPI + GitHub Release"

# Push to main
git branch -M main
git push -u origin main
```

**Verify:** Open `https://github.com/farkusza/ports-registry` in your browser. You should see the README rendered, all 6 new files, and the Actions tab showing the CI run kicked off.

---

## 3. Watch the first CI run

```bash
# In one terminal — wait for it to finish
gh run watch

# Or with curl + token
SHA=$(git rev-parse HEAD)
while true; do
  STATUS=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
    "https://api.github.com/repos/kyle-farkus/ports-registry/commits/$SHA/status" \
    | python -c "import sys,json; print(json.load(sys.stdin)['state'])")
  echo "$(date +%H:%M:%S)  $STATUS"
  [ "$STATUS" = "success" ] || [ "$STATUS" = "failure" ] && break
  sleep 20
done
```

**Expected outcome:**
- `test` matrix: 6 jobs (Ubuntu × 3.10/3.11/3.12, Windows × same) — all green
- `build-exe` job: green, artifact `ports-windows-exe` available on the run page
- `publish-pypi` + `github-release`: **skipped** (no `v*` tag yet — that's correct)

---

## 4. Tag v0.1.0

```bash
git tag -a v0.1.0 -m "ports-registry 0.1.0"
git push origin v0.1.0
```

This re-triggers CI. The `publish-pypi` and `github-release` jobs will now run **but will fail on PyPI** until you complete step 5. The `.exe` release will work regardless.

**Verify:** Open `https://github.com/kyle-farkus/ports-registry/releases` — a draft release for v0.1.0 should exist with `ports.exe` attached.

---

## 5. PyPI trusted publishing setup (one-time, browser)

This is the bit PyPI needs to authorise *this repo's* workflow to push packages *as you*. One-time, browser-only, ~2 minutes.

### 5.1 Register the project on PyPI (first time only)

1. Open **https://pypi.org/account/register/** (or sign in if you already have an account)
2. Enable 2FA (PyPI requires it for publishing)
3. After login, open **https://pypi.org/manage/projects/**

For a brand new project name (`ports-registry`), PyPI will refuse to upload until the project is *manually* claimed via the dashboard OR until a trusted publisher is configured. We'll do the latter — go to step 5.2.

### 5.2 Add a trusted publisher

1. Go to **https://pypi.org/manage/account/publishing/**
2. Scroll to **Add a new pending publisher** (or **Add a new trusted publisher** depending on UI)
3. Fill in exactly:
   - **PyPI Project Name:** `ports-registry`
   - **Owner:** `farkusza`
   - **Repository name:** `ports-registry`
   - **Workflow filename:** `ci.yml`
   - **Environment name:** `pypi`  ← must match the `environment:` block in `.github/workflows/ci.yml`
4. Click **Add**

### 5.3 Create the `pypi` environment in GitHub

1. Open **https://github.com/settings/environments/new**
2. Name: `pypi`
3. Under **Deployment branches**, select **Selected branches** → branch pattern `v*` (matches `v0.1.0`, `v0.1.1`, etc.)
4. Click **Configure environment**
5. (Optional) Add protection rules — e.g. required reviewers. Skip for solo projects.

### 5.4 Re-trigger the failed publish job

After saving, the previously failed publish-pypi job won't auto-retry. Re-tag:

```bash
# Delete the old tag locally and remotely
git tag -d v0.1.0
git push origin :refs/tags/v0.1.0

# Re-tag and push
git tag -a v0.1.0 -m "ports-registry 0.1.0"
git push origin v0.1.0
```

**Verify:**
- CI run shows `publish-pypi` ✅
- `https://pypi.org/project/ports-registry/` is live — anyone can now `pip install ports-registry`
- `https://github.com/farkusza/ports-registry/releases/tag/v0.1.0` has `ports.exe` attached

---

## 6. Smoke test the published artifacts

After everything is green:

```bash
# Pip install from PyPI
pip install ports-registry
ports --help
ports list

# Download + run the .exe (in a different shell / VM if you want to be paranoid)
curl -L -o ports.exe https://github.com/kyle-farkus/ports-registry/releases/latest/download/ports.exe
./ports.exe --help
./ports.exe list
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `git push` asks for password | You didn't complete step 0.2. Re-do the credential helper setup. |
| `remote: Permission to farkusza/ports-registry denied` | Token missing `repo` scope. Regenerate. |
| `403 Forbidden` on `gh repo create` | Token missing `repo` scope. |
| PyPI publish job fails with `403 Forbidden` | Trusted publisher not configured. Re-do step 5.2. |
| PyPI says "project not found" | First-time project claim wasn't done. Either register it manually via the dashboard, or trust that the trusted publisher will create it on first upload. |
| `gh` command not found | Use the `curl` paths in section 1b, 3, and 5.4. |
| `.exe` release is empty | Check that the `build-exe` job ran before `github-release`. They should be ordered via `needs:`. |