# Releasing

How to publish a new version of Dictator.app that every installed copy will
offer as an update. This is for maintainers.

## How updates reach users

Installed apps use [Sparkle](https://sparkle-project.org). They read
`appcast.xml` from the latest GitHub release (or from the R2 bucket, once
`DICTATOR_DOWNLOAD_BASE` is set) and take an update only when:

1. its `.dmg` is signed with the Sparkle update key, and
2. its build number is higher than their own.

The app inside is signed with the one release certificate, so users keep their
Microphone and Accessibility grants across the update.

## Secrets you must keep

Everything lives in `~/.dictator-release`, outside the repo. Back these up
somewhere safe and never commit them:

| File | What it is | If it is lost |
|---|---|---|
| `release.p12` + `release.pass` | the self-signed "Dictator Release" certificate | every user loses their permissions on the next update |
| `sparkle_ed25519.key` | the Sparkle EdDSA update key | installed apps refuse every future update |

`tools/release_cert.sh create` makes the certificate once, ever. Do not run it
again on a project that has shipped.

The same material is in the repository secrets for CI:

| Secret | Contents |
|---|---|
| `DICTATOR_P12_BASE64` | `release.p12`, base64 |
| `DICTATOR_P12_PASSWORD` | `release.pass` |
| `DICTATOR_SPARKLE_ED_KEY` | `sparkle_ed25519.key` |
| `CF_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `CF_PAGES_DEPLOY_HOOK` | Cloudflare R2 and Pages, only used when the `DICTATOR_DOWNLOAD_BASE` repository variable is set |

Local runs read the same names from `.env`. `.env.example` lists all of them.

## Before you release

- You are on `main`, the tree is clean, and `main` is pushed. The script
  refuses otherwise, so every release is a commit anyone can check out.
- CI is green on that commit.
- The version is higher than the last one (`0.1.7` → `0.1.8`).

## Release from your Mac

```bash
tools/release.sh 0.1.8 [notes.md]
```

It does, in order:

1. builds `build/Dictator-0.1.8.dmg`, signed with the release certificate
2. signs the `.dmg` with the Sparkle key and writes `build/appcast.xml`
3. creates the GitHub release `v0.1.8` with the `.dmg` (also as
   `Dictator.dmg`, which the README download link uses), its SHA256 and the feed
4. with `DICTATOR_DOWNLOAD_BASE` set, uploads the same files to R2 and asks
   Cloudflare Pages to rebuild the website (`tools/publish_r2.sh`)

It needs a GitHub token in `GH_TOKEN` or in `.env`.

## Release from CI

Push a tag on a commit that is on `main`:

```bash
git tag v0.1.8 && git push origin v0.1.8
```

The `dmg` job in `.github/workflows/release.yml` builds, signs and publishes
the same files. A tag that is not on `main`, or a tag pushed without the
secrets, fails instead of publishing. If `tools/release.sh` already published
that tag, CI sees the feed on the release and does not publish again.

## Guards that stop a bad release

| Guard | Where | Why |
|---|---|---|
| Releases only from `RELEASE_BRANCHES` (`main`) | workflow env, read by `tools/release.sh` | one line of history, one build number sequence |
| Build number must go up | `tools/appcast.sh` | apps ignore an update with a lower build number, forever |
| No ad-hoc signature on a tag | workflow | an ad-hoc build drops every user's permissions |
| No feed without the Sparkle key | workflow | a release without a signed feed breaks updates for everyone |

The build number is the commit count of the branch. That is why pull requests
are merged with merge commits, never squashed: a squash can lower the count.

## After releasing

- Check the release page has `Dictator.dmg`, `Dictator-<VERSION>.dmg`, the
  `.sha256` and `appcast.xml`.
- On a Mac with the previous version: Dictator → Check for Updates. It should
  offer the new one, install it, and keep working without asking for
  permissions again.
- If a release went out broken, publish a fixed one with a higher version.
  Do not delete the release: apps read the feed from the latest release, and
  removing it leaves them pointed at the one before.
