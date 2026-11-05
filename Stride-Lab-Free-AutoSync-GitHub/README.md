# Stride Lab Live — FREE Garmin Auto-Sync on GitHub

A **read-only public running dashboard** that automatically collects your own Garmin Personal API activity history and republishes the dashboard every 6 hours. It runs on **GitHub Actions + GitHub Pages**, with **no paid server and no need to keep your PC on**.

Unlike the local Stride Lab application, the public website deliberately cannot change Garmin credentials, delete activity data or expose individual FIT recordings. The Garmin key never enters the browser or published website.

## Before you start

- A GitHub account; a **public GitHub repository** (GitHub Pages on the free personal plan).
- Your existing Garmin Connect **Personal API key** (do not add it to source files).
- Python installed on your computer (only for generating an encryption key once; your running PC is not needed afterward).
- Optional: GitHub Desktop (makes uploading all files, including `.github/workflows`, easier).

## Get online in 6 steps

### 1. Create the GitHub repository

In GitHub, create a **new PUBLIC repository**, e.g. `stride-lab-live`. Leave it empty. A public repo means anyone can see the source code and *encrypted* archive file. They cannot see decrypted activity history without your private encryption secret. Your public website is also visible to anyone.

Recommended on Windows: install [GitHub Desktop](https://desktop.github.com/), choose **File → Clone repository**, clone the empty repo, then copy **everything inside this downloaded project folder** into the cloned repo (including the hidden `.github` folder). In GitHub Desktop, commit and **Push origin**.

Alternative via Git command line from an extracted copy:

```bash
git init
git branch -M main
git add .
git commit -m "Start Stride Lab automatic Garmin dashboard"
git remote add origin https://github.com/YOUR_USERNAME/stride-lab-live.git
git push -u origin main
```

Replace YOUR_USERNAME. If GitHub Desktop has already created the repository, **don't** run `git init` again.

### 2. Generate a history encryption key

On your computer, open a terminal in this folder and run:

```bash
python -m pip install cryptography
python generate_archive_key.py
```

Copy the output and keep it in a secure password manager. Do not commit or share it. This is **separate from your Garmin API key**. You must keep it to decrypt historical training records in future.

### 3. Add two GitHub Actions secrets

On GitHub, open **your repository → Settings → Secrets and variables → Actions → Secrets → New repository secret**. Create exactly:

| Secret name | Value |
| --- | --- |
| `GARMIN_PERSONAL_API_KEY` | Your existing Garmin Connect Personal API key |
| `STRIDE_ARCHIVE_KEY` | The encryption key generated in step 2 |

**Never paste these secrets into a file, commit, issue, pull request or Pages settings.** GitHub Actions passes them privately to the scheduled sync runner.

**Optional public-sharing variables** (Repository → Settings → Secrets and variables → Actions → Variables):

| Variable | Default | Effect when set to `true` |
|---|---|---|
| `PUBLISH_PHYSIOLOGY` | `false` | Shares Garmin-configured max HR, resting HR, LTHR, calculated zone ranges, zone-time summaries and threshold pace where available. |
| `PUBLISH_ACTIVITY_SUMMARIES` | `false` | Shares a browsable list of run **dates**, distances, durations, paces and ascent; average HR is included only if physiology sharing is also enabled. |

**Privacy warning:** GitHub Pages is publicly accessible under a free personal GitHub account, even if your source repository is private. These options publish data in a downloadable JSON file. Do not enable them assuming a GitHub Pages page is password protected. Neither option publishes your Garmin key, named workouts, activity IDs, FIT recordings, GPS routes or exact activity start times.

### 4. Enable GitHub Pages

Repository → **Settings → Pages → Build and deployment → Source: GitHub Actions**. Save.

### 5. Run the very first sync

Repository → **Actions** → **Garmin auto-sync and publish Stride Lab** → **Run workflow** → choose `main` → Run workflow.

Open the run and check the logs. The workflow downloads Garmin activity summaries, then up to 60 detailed FIT recordings per run. If you have hundreds of runs, **several scheduled runs may be required for complete FIT coverage**. The public dashboard shows how many FIT streams are still pending. Garmin zone values only appear if supported by the API and explicitly enabled for public display.

The workflow automatically:

1. Exchanges your Garmin key for a temporary access token.
2. Fetches the activity list (full historical scan on its first successful run, then up to 300 recent activities per subsequent run).
3. Imports up to 60 pending detailed FIT files per run.
4. Calculates fastest recorded running efforts, mileage, consistency and guidance.
5. Encrypts the private SQLite data and commits **only the ciphertext** to the repository.
6. Builds a **sanitised public website** and deploys it with GitHub Pages.

### 6. Share your website

After the first green workflow run, visit:

`https://YOUR_USERNAME.github.io/stride-lab-live/`

Replace the username and repository name. You can also find the exact link under **Settings → Pages** or the GitHub Actions deployment result. The page checks for newly published statistics every 15 minutes while open.

**That's it.** Each six-hourly scheduled run can collect more details and rebuild the site. Your Windows PC does not have to be on.

## What is free and what is not

- GitHub Pages is included for **public repositories** on GitHub Free.
- GitHub Actions scheduled workflows on public repositories are free on standard GitHub-hosted runners, subject to GitHub's usage policies and limits.
- A custom domain is not required; the `.github.io` subdomain is included.
- GitHub scheduled runs can be delayed or skipped; this is **not real-time syncing** or a guaranteed service-level agreement.
- Garmin API keys have expiration dates (up to one year). Replace your GitHub secret when Garmin issues a new key, then rerun the workflow. Preserve your `STRIDE_ARCHIVE_KEY`.
- Monitor the Actions tab occasionally. GitHub may disable scheduled workflows in certain inactivity scenarios.

## What is and isn't published

**Published:** aggregate running volume, total runs, weekly/monthly distance, personal bests (time/pace/date), non-sensitive training insights, race projections and summary coverage. Garmin configured max HR, resting HR, threshold HR, HR zones and aggregated HR charts are published *only if* `PUBLISH_PHYSIOLOGY=true`. The dated run summary table is published *only if* `PUBLISH_ACTIVITY_SUMMARIES=true`.

**Not published in website:** Garmin key, access tokens, named workouts, activity IDs, FIT samples, GPS tracks or raw activity JSON. The encrypted archive file **is committed to the public source repository**. This design protects the underlying records with a separate encryption key held in GitHub Actions Secrets; anyone who obtains that encryption key could decrypt the archive.

The local Stride Lab app stays completely separate, with its private settings and manually entered race PBs. This cloud package imports Garmin data independently. It does **not** automatically transfer your manual local physiology overrides or official race records. Stride Lab's PBs may change while detailed FIT streams are still downloading.

This is a personal-sharing application, not a multi-user Garmin integration. It uses your own Garmin Personal API key only. Always check the current Garmin terms before publishing data externally.

## Troubleshooting

**Workflow says `Missing GARMIN_PERSONAL_API_KEY`** → Check the Actions secret name exactly. The secret should be in your repo, not a variable or a `.env` file.

**`Unable to decrypt saved history`** → You probably changed `STRIDE_ARCHIVE_KEY`. Restore the *original* value. Don't regenerate the encryption key unless you are deliberately discarding prior cloud history.

**`Garmin rejected the key (HTTP 401)`** → Verify the Personal API key is still active in Garmin Connect and update the GitHub secret if needed. This is separate from the encryption key.

**Page shows no data** → Check that your first GitHub Actions run succeeded and **Settings → Pages** uses GitHub Actions. The publishing step only executes after a successful Garmin sync.

**Website only has some personal bests** → Watch the FIT coverage displayed on the site. First import processes 60 detailed runs per scheduled run. Six-hourly runs continue backfilling until complete, except where Garmin doesn't offer FIT data.

**How to sync immediately** → GitHub → Actions → Garmin auto-sync and publish Stride Lab → Run workflow. There is no Garmin key entry field on the public website.

**My site is public but I want it private** → Don't use GitHub Pages as an access-controlled private dashboard. Stop Pages or choose a separate authenticated hosting architecture. Robots directives are *not* privacy protection.

## Developer tests

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
node --check site_assets/app.js
```

The tests use synthetic Garmin data and never call Garmin. No live account has been tested without your key.

## Technical outline

- `cloud_sync.py`: scheduled import, physiology source selection, encrypted persistence, static export
- `server/`: Garmin Personal API client, SQLite model, FIT reader, deterministic analytics from Stride Lab
- `public_export.py`: allowlisted public output; explicitly strips activity IDs, names, GPS and secrets
- `site_assets/`: static responsive read-only dashboard with no third-party JavaScript or external trackers
- `.github/workflows/garmin-sync.yml`: scheduled sync and GitHub Pages deployment
- `state/history.enc`: encrypted private history, created only after your first successful run

**Caution:** GitHub Pages exposes published statistics to anyone, including bots, even though the site includes `noindex` recommendations.
