# Releasing

How to publish a new version of Dictator.app that every installed copy will
offer as an update. This is for maintainers.

## Where releases live

| What | Where |
|---|---|
| The code | `cc-vb/dictator`, private |
| What people download, and the feed installed apps read | the Cloudflare R2 bucket, `DICTATOR_DOWNLOAD_BASE` |
| An archive of every version | GitHub releases in the code repo, private, for maintainers |

The bucket holds only the newest release: `Dictator-<VERSION>.dmg`,
`latest.json` (what the website shows) and `appcast.xml`. Setting it up, and
the usage alerts, are in [`cloudflare-r2.md`](cloudflare-r2.md).

`tools/build_dmg.sh` writes the feed address into the app: the website's
`/appcast.xml` when `DICTATOR_SITE_URL` is set (it redirects into the
bucket), otherwise the bucket's own. Pick the address before the first
release people install: changing it later takes a release that both old and
new addresses serve, so every installed app moves over.

## How updates reach users

Installed apps use [Sparkle](https://sparkle-project.org). They read
`appcast.xml` from the bucket (through the website, when it is set) and take
an update only when:

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
| `CF_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` | the R2 upload key and bucket |
| `CF_PAGES_DEPLOY_HOOK` | rebuilds the website from `main` after a release |

And repository variables: `DICTATOR_DOWNLOAD_BASE` and `DICTATOR_SITE_URL`.

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
3. uploads the `.dmg`, `latest.json` and the feed to R2, deletes the previous
   `.dmg`, and asks Cloudflare Pages to rebuild the website
   (`tools/publish_r2.sh`)
4. creates the archive release `v0.1.8` in the code repo, with the `.dmg`
   (also as `Dictator.dmg`), its SHA256 and the feed

It needs the R2 keys and a GitHub token that can write to the private repo
(the `repo` scope), in the environment or `.env`.

## Release from CI

Push a tag on a commit that is on `main`:

```bash
git tag v0.1.8 && git push origin v0.1.8
```

The `dmg` job in `.github/workflows/release.yml` builds, signs, uploads to R2
and then writes the archive release. Nothing else runs CI: no push and no pull
request, so runner minutes are only spent on releases. A tag that is not on
`main`, or a tag pushed without the secrets and the bucket's address, fails in
the first job instead of publishing. If `tools/release.sh` already published
that tag, CI sees the feed on the archive release and does not publish again.

## Guards that stop a bad release

| Guard | Where | Why |
|---|---|---|
| Releases only from `RELEASE_BRANCHES` (`main`) | workflow env, read by `tools/release.sh` | one line of history, one build number sequence |
| Build number must go up | `tools/appcast.sh` | apps ignore an update with a lower build number, forever |
| No ad-hoc signature on a tag | workflow | an ad-hoc build drops every user's permissions |
| No feed without the Sparkle key | workflow | a release without a signed feed breaks updates for everyone |
| No release without the bucket and its keys | workflow, first job | fails in a minute on Linux instead of after the macOS build |

The build number is the commit count of the branch. That is why pull requests
are merged with merge commits, never squashed: a squash can lower the count.

## After releasing

- `$DICTATOR_DOWNLOAD_BASE/appcast.xml` opens as XML and names the new version,
  and the website's download gives `Dictator-<VERSION>.dmg`.
- On a Mac with the previous version: Dictator → Check for Updates. It should
  offer the new one, install it, and keep working without asking for
  permissions again.
- If a release went out broken, publish a fixed one with a higher version.
  Do not put an older feed back: apps ignore a lower build number, so it
  fixes nothing and hides the problem.
