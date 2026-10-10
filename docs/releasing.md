# Releasing

How to publish a new version of Dictator.app that every installed copy will
offer as an update. This is for maintainers.

## Where releases live

The code is in a private repo, `cc-vb/dictator-app`. Releases are published to
a public repo that holds no code, `cc-vb/dictator`, named by the
`DICTATOR_RELEASES_REPO` variable. It has the name the code repo used to have,
so every installed app, which checks
`github.com/cc-vb/dictator/releases/latest/download/appcast.xml`, keeps
finding its updates without a release that moves it.

The website reads the newest release from the same repo when it builds.

Serving releases from Cloudflare R2 instead is set up but switched off; how to
turn it on is in [`cloudflare-r2.md`](cloudflare-r2.md).

## How updates reach users

Installed apps use [Sparkle](https://sparkle-project.org). They read
`appcast.xml` from the latest release in the releases repo (or from the R2
bucket, once `DICTATOR_DOWNLOAD_BASE` is set) and take an update only when:

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
| `RELEASES_TOKEN` | fine-grained token, Contents read and write on the releases repo only; it expires, so renew it before it does |
| `CF_PAGES_DEPLOY_HOOK` | optional: rebuilds the website after a release |
| `CF_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` | Cloudflare R2, only used when the `DICTATOR_DOWNLOAD_BASE` repository variable is set |

And one repository variable: `DICTATOR_RELEASES_REPO` = `cc-vb/dictator`.

Local runs read the same names from `.env`. `.env.example` lists all of them.

## Before you release

- You are on `main`, the tree is clean, and `main` is pushed. The script
  refuses otherwise, so every release is a commit anyone can check out.
- The tests pass on that commit: `python3 -m pytest -q tests`. CI runs them
  again inside the release and stops it if one fails.
- The version is higher than the last one (`0.1.7` → `0.1.8`).

## Release from your Mac

```bash
tools/release.sh 0.1.8 [notes.md]
```

It does, in order:

1. builds `build/Dictator-0.1.8.dmg`, signed with the release certificate
2. signs the `.dmg` with the Sparkle key and writes `build/appcast.xml`
3. pushes the tag `v0.1.8` to the code repo, and creates the release `v0.1.8`
   in the releases repo with the `.dmg` (also as `Dictator.dmg`, which the
   README download link uses), its SHA256 and the feed
4. with `DICTATOR_DOWNLOAD_BASE` set, uploads the same files to R2 and asks
   Cloudflare Pages to rebuild the website (`tools/publish_r2.sh`)

It needs a GitHub token in `GH_TOKEN` or in `.env` that can write to the
releases repo.

## Release from CI

Push a tag on a commit that is on `main`:

```bash
git tag v0.1.8 && git push origin v0.1.8
```

The `dmg` job in `.github/workflows/release.yml` builds, signs and publishes
the same files to the releases repo, then asks Cloudflare Pages to rebuild the
website when `CF_PAGES_DEPLOY_HOOK` is set. Nothing else runs CI: no push and
no pull request, so runner minutes are only spent on releases. A tag that is not on `main`, or a tag pushed without the
secrets, fails instead of publishing. If `tools/release.sh` already published
that tag, CI sees the feed on the release and does not publish again.

## Guards that stop a bad release

| Guard | Where | Why |
|---|---|---|
| Releases only from `RELEASE_BRANCHES` (`main`) | workflow env, read by `tools/release.sh` | one line of history, one build number sequence |
| Build number must go up | `tools/appcast.sh` | apps ignore an update with a lower build number, forever |
| No ad-hoc signature on a tag | workflow | an ad-hoc build drops every user's permissions |
| No feed without the Sparkle key | workflow | a release without a signed feed breaks updates for everyone |
| No release to another repo without `RELEASES_TOKEN` | workflow, first job | fails in a minute on Linux instead of after the macOS build |

The build number is the commit count of the branch. That is why pull requests
are merged with merge commits, never squashed: a squash can lower the count.

## After releasing

- Check the release page in the releases repo has `Dictator.dmg`, `Dictator-<VERSION>.dmg`, the
  `.sha256` and `appcast.xml`.
- On a Mac with the previous version: Dictator → Check for Updates. It should
  offer the new one, install it, and keep working without asking for
  permissions again.
- If a release went out broken, publish a fixed one with a higher version.
  Do not delete the release: apps read the feed from the latest release, and
  removing it leaves them pointed at the one before.
