# Serving releases from Cloudflare R2

Releases are served from the public GitHub repo `mynk03/dictator` today (see
[`releasing.md`](releasing.md#where-releases-live)). Everything needed to serve
them from a Cloudflare R2 bucket instead is already in the code and switched
off. This page is how to switch it on, and back off.

## Why you might switch

| | GitHub releases repo (now) | Cloudflare R2 |
|---|---|---|
| Card on file | no | yes, R2 asks for one even on the free tier |
| Cost | free | free up to 10 GB stored and 10 million downloads a month; egress is free |
| `appcast.xml` opened in a browser | downloads with an "insecure download" warning, because GitHub serves release files as attachments | shows as XML, no warning |
| Download address | `github.com/...` | your own domain |
| Old versions | every release is kept | only the newest `.dmg` is kept |
| Download counts | per file, from the GitHub API | Cloudflare analytics on the custom domain |

The warning never affects the app: Sparkle reads the feed either way. Switch
for the address and the clean feed, not for the app.

Gatekeeper's "Open Anyway" step is the same on both. Only notarization
(Apple Developer Program) removes it.

## Before you start

- **A domain on Cloudflare.** The address the app checks for updates is
  written into every build, so it has to be one you keep. The bucket's free
  `r2.dev` address is rate limited and not meant for real traffic, and a
  `*.pages.dev` address would have to be moved again once you buy a domain.
- **The website on Cloudflare Pages**, set up as in
  [`website/README.md`](../website/README.md#deploy-cloudflare-pages).

## What is already built

| Piece | What it does with R2 on |
|---|---|
| `tools/publish_r2.sh` | uploads `Dictator-<VERSION>.dmg`, `latest.json` and `appcast.xml` to the bucket, deletes the previous `.dmg`, asks Pages to rebuild |
| `tools/appcast.sh` | the feed points at the `.dmg` in the bucket; the build number check reads the bucket's feed, falling back to GitHub's |
| `tools/build_dmg.sh` | writes `SUFeedURL = $DICTATOR_SITE_URL/appcast.xml` into the app |
| `website/scripts/sync-latest.mjs` | reads `latest.json` from the bucket; `/download/mac` and `/appcast.xml` on the site redirect into it |
| `.github/workflows/release.yml` | the "Publish to Cloudflare R2" step runs |

All of it is keyed on one repository variable, `DICTATOR_DOWNLOAD_BASE`.
Empty, none of it runs.

## Set up Cloudflare

1. **R2 → Create bucket**, for example `dictator-downloads`.
2. **Bucket → Settings → Custom Domains → Connect Domain**, for example
   `downloads.example.com`. That address is `DICTATOR_DOWNLOAD_BASE`.
3. **R2 → Manage R2 API Tokens → Create API token**, Object Read & Write,
   limited to that bucket. Note the access key ID and secret, and the account
   ID shown on the R2 page.
4. **Pages → your site → Settings → Builds → Deploy hooks**, create one for
   `main`. That URL is `CF_PAGES_DEPLOY_HOOK` (you may already have it).
5. **Pages → your site → Settings → Variables**: add `DICTATOR_DOWNLOAD_BASE`
   and `DICTATOR_SITE_URL` (your domain, for example `https://example.com`).
   Keep `DICTATOR_RELEASES_REPO`: the site falls back to it until the bucket
   has its first release.

## Set up GitHub

In the private code repo, **Settings → Secrets and variables → Actions**:

| Kind | Name | Value |
|---|---|---|
| Variable | `DICTATOR_DOWNLOAD_BASE` | `https://downloads.example.com` |
| Variable | `DICTATOR_SITE_URL` | `https://example.com` |
| Secret | `CF_ACCOUNT_ID` | account ID |
| Secret | `R2_ACCESS_KEY_ID` | from step 3 |
| Secret | `R2_SECRET_ACCESS_KEY` | from step 3 |
| Secret | `R2_BUCKET` | `dictator-downloads` |
| Secret | `CF_PAGES_DEPLOY_HOOK` | from step 4 |

For releases made from your Mac, put the same names in `.env`.

## The switch

Release as usual (`git tag vX.Y.Z && git push origin vX.Y.Z`). That one
release:

1. is still published to the GitHub releases repo, so every installed app
   finds it on the address it checks today;
2. is uploaded to the bucket, with its feed;
3. carries the new feed address (`https://example.com/appcast.xml`) inside the
   app, so after updating, an app checks the website from then on.

Nobody is stranded: releases keep going to GitHub as well, so an app that
skips this update finds the next one there and moves over with it.

Check, after the release:

- `https://example.com/appcast.xml` opens as XML and names the new version.
- `https://example.com/download/mac` downloads `Dictator-X.Y.Z.dmg`.
- On a Mac with the previous version, Check for Updates offers and installs
  it, and after that `defaults read <app>/Contents/Info SUFeedURL` shows the
  website's address.

Keep the GitHub releases repo public and receiving releases for as long as
any old copy may still be out there. It costs nothing.

## Switching back

Empty the `DICTATOR_DOWNLOAD_BASE` and `DICTATOR_SITE_URL` variables. The next
build points the app at the GitHub feed again. Until every app has that
build, keep the bucket and the website's `/appcast.xml` working, because apps
that took an R2 release still check the website.
