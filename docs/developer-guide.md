# Developer guide

How Dictator is put together, how a change reaches people, and the limits
that are there on purpose. Written for a developer working with an AI
assistant (Claude Code or similar): the [rules for the assistant](#rules-for-the-assistant)
at the end are the ones it must follow, and `CLAUDE.md` at the root points it
here.

Details live in [`CONTRIBUTING.md`](CONTRIBUTING.md) (set up, tests, commits),
[`releasing.md`](releasing.md) (the release itself) and
[`cloudflare-r2.md`](cloudflare-r2.md) (hosting and costs). This page is the
map.

## What is in the repo

| Part | Path | Commit scope |
|---|---|---|
| The Mac app and its Swift helpers | `native/` | `app` |
| dictator core: the Python package (dictation loop, CLI, library) | `dictator_core/` | `dictator-core` |
| The website, React, prerendered | `website/` | `website` |
| Documentation | `docs/` | `docs` |
| Build and release scripts | `tools/` | the part they serve |
| Tests | `tests/` | the part they test |

Commit messages are `type(scope): summary` with a bullet-point body; see
[`CONTRIBUTING.md`](CONTRIBUTING.md#commit-messages).

## Where things live

| What | Where | Who can see it |
|---|---|---|
| The code | GitHub `cc-vb/dictator` | the team |
| The `.dmg` people download, `latest.json`, `appcast.xml` | Cloudflare R2 bucket `dictator-downloads`, at `DICTATOR_DOWNLOAD_BASE` | everyone |
| The website | Cloudflare Pages project `dictator`, `https://dictator.pages.dev`, built from `main` | everyone |
| Every released version | GitHub releases in `cc-vb/dictator` | the team: an archive, nothing reads it |
| Addresses and keys | repository variables and secrets on GitHub; `.env` locally | maintainers |

Installed apps check `https://dictator.pages.dev/appcast.xml` for updates. The
website redirects that into the bucket, so the storage can move later without
moving any installed app.

## How a release reaches people

```
git tag v0.1.11 && git push origin v0.1.11        (on main)
  │
  ▼  .github/workflows/release.yml
  check     Linux, under a minute: the tag is on main, the R2 settings exist
  tests     macOS: python3 -m pytest -q tests
  native    macOS: Swift helpers and whisper.cpp
  app       macOS: the app executable
  dmg       macOS: assemble, sign, package, sign the update feed
            → R2: Dictator-0.1.11.dmg, latest.json, appcast.xml
            → GitHub release v0.1.11 (the private archive)
  website   asks Cloudflare Pages to rebuild (deploy hook)
  │
  ▼  Cloudflare Pages builds website/ from main
  the site reads latest.json from the bucket: version, size, SHA256, link
  │
  ▼  installed apps, on their next check
  read appcast.xml, see a higher build number, install the signed update
```

A website-only change (copy, design) is merged to `main`, then:

```bash
git tag website-2026-10-11 && git push origin website-2026-10-11
```

That only rebuilds the site. Nothing else runs it.

## What starts a build or a deployment

Only a tag does. Everything else is quiet on purpose.

| You do | What happens |
|---|---|
| Open a pull request, or push a branch | nothing: no CI, no website build |
| Merge into `main` | nothing, until a tag asks for it |
| Push a `v…` tag on `main` | the app release: tests, build, sign, upload to R2. Then, **only if all of that succeeded**, the website rebuilds and shows the new version |
| Push a `website-…` tag on `main` | only the website rebuilds |
| Push either tag anywhere but `main` | refused in the first minute |

This depends on two settings in Cloudflare, under **Workers & Pages →
dictator → Settings → Builds → Branch control**:

- production branch `main`, **automatic deployments off**: a merge does not
  rebuild the site; the deploy hook does;
- preview branch **None**: branches and pull requests get no preview build.

Cloudflare does not charge for builds, but the free plan allows 500 a month
and every build counts, previews included. Past that, the site stays as it is
until the next month. Turning previews back on would spend that allowance on
every push.

## Limits that are there on purpose

Everything public runs on free allowances (GitHub Actions minutes, Cloudflare
Pages builds, R2 reads). These limits keep it that way. Do not loosen one
without the maintainers agreeing, and do not let an assistant do it as a side
effect of something else.

| Limit | Where it is set | Why |
|---|---|---|
| **The bucket keeps only the newest release and the one before it.** Older `.dmg` files are deleted when a new one is published. | `tools/publish_r2.sh` | storage and a single "latest" to point at; the previous one stays so a site that has not rebuilt yet still downloads |
| **Older versions are not downloadable by the public.** They are only in the private GitHub releases. | by design | people get the newest version, and installed apps update themselves |
| **Apps check for updates on their own every two days.** | `SUScheduledCheckInterval` in `native/app/Info.plist` | every check is a paid read on the bucket |
| **"Check for Updates" by hand works 10 times a day per Mac.** | `Updater.manualLimit` in `native/app/Updater.swift` | so one person clicking cannot run the reads up |
| **CI runs only on a `v*` or `website-*` tag on `main`.** No runs on push or pull request. | `.github/workflows/*.yml` | macOS runner minutes are the expensive ones |
| **The website rebuilds only when asked.** Automatic deployments are off in Cloudflare; a tag or a release calls the deploy hook. | Cloudflare Pages settings, `.github/workflows/website.yml` | 500 builds a month on the free plan |
| **Releases come from `main` only.** A tag anywhere else is refused in the first minute. | `RELEASE_BRANCHES` in `release.yml` | one history, one build number sequence |

What it costs and how far the free allowance goes is in
[`cloudflare-r2.md`](cloudflare-r2.md#what-it-costs).

## Releasing a new version

1. Everything for it is merged to `main` with **a merge commit, never a
   squash**: the app's build number is the commit count of `main`, and a
   squash can lower it, after which installed apps ignore every update.
2. The tests pass locally: `python3 -m pytest -q tests`. CI runs them again
   inside the release, but nothing runs them on a pull request.
3. The version is higher than the last one. See the newest at
   `https://dictator.pages.dev` or `git tag --sort=-v:refname | head -1`.
4. Tag and push, from an up-to-date `main`:
   ```bash
   git checkout main && git pull
   git tag v0.1.11 && git push origin v0.1.11
   ```
5. Watch **Actions** on GitHub: `release` (about 10 minutes), then `website`.
6. Check: the site shows the new version and its download works;
   `https://dictator.pages.dev/appcast.xml` names it; on a Mac with the
   previous version, Dictator → Check for Updates offers it and keeps the
   Microphone and Accessibility permissions.

A release that went out broken is fixed by releasing a higher version. Do not
delete a release or put an older feed back: apps never take a lower build
number.

## Rules for the assistant

These are the things an assistant has got wrong in this repo, or would cost
real users if it did. Follow them as written.

**Ask the human first, every time:**
- before pushing a tag (`v*` or `website-*`): it publishes to every user or
  rebuilds the public site;
- before calling the Cloudflare deploy hook, uploading to or deleting from the
  bucket, or running `tools/release.sh` / `tools/publish_r2.sh`;
- before changing any limit in the table above;
- before pushing to `main` or merging a pull request.

**Never:**
- print, log, commit or paste a secret: `.env` values, the signing
  certificate, the Sparkle key, Cloudflare and GitHub tokens. Read `.env` only
  when the human asks, and refer to values by name;
- change the signing identity, `SUPublicEDKey` or the Sparkle key: every
  user's permissions or every future update depend on them
  ([`CONTRIBUTING.md`](CONTRIBUTING.md#rules));
- squash-merge, or rewrite history that is already pushed;
- add a network call for speech, text or anything a user says: no audio or
  text leaves the Mac;
- delete releases, bucket files or anything under `~/.dictator`.

**Tests and the user's data.** The tests must never touch `~/.dictator`.
`tests/conftest.py` points every module's files at a temporary folder, and it
imports each module by name to do so. When that import failed silently after
the package was renamed, one test run wiped a maintainer's real dictation
history. So:
- after renaming or moving a module, update `tests/conftest.py` first, and
  run the suite with a throwaway home and state folder until it is green:
  ```bash
  UB=$(python3 -m site --user-base)
  HOME=$(mktemp -d) DICTATOR_STATE=$(mktemp -d) PYTHONUSERBASE=$UB python3 -m pytest -q tests
  ```
- never wrap that import in a `try`/`except` again.

**Working in the repo:**
- `.env` follows `.env.example` exactly: same names, same order, each once.
  Add a new variable to `.env.example` first; check with `tools/check_env.sh`
  (it prints names, never values).
- Two sessions in one checkout switch each other's branches. Give a second
  session its own folder: `git worktree add ../dictator-<topic> <branch>`.
- The app must build with Apple's command line tools alone
  (`tools/build_app.sh build/appbin`), without full Xcode.
- To look at the app's windows without dictating, run the built binary with
  `DICTATOR_FAKE=1 DICTATOR_FIXTURES=$PWD/native/app/Fixtures`; the numbers
  are sample data, not the user's.
- The website runs locally with `cd website && pnpm dev`. It must also build
  from a fresh clone, which is what Cloudflare does.
- Commit with the `type(scope): summary` format, one part of the repo per
  commit where possible.
