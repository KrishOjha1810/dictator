# Dictator website

The public site for Dictator: the landing page, the install guide, every
release with its checksum, and the download links.

It is a static [Astro](https://astro.build) site. There is no server and no
database; the build writes plain HTML to `dist/`, which Cloudflare Pages
serves.

## Run it

```bash
cd website
pnpm install
pnpm dev            # http://localhost:4321
```

## Where the version numbers come from

Nothing on the site hard-codes a version. `scripts/sync-releases.mjs` reads the
published releases and writes two files:

| File | What it holds |
|---|---|
| `src/data/releases.json` | every version: date, size, SHA256, file URL, minimum macOS |
| `public/_redirects` | the stable download links, pointed at the current files |

The download buttons always link to our own addresses, never to a file host
directly:

| Link | Goes to |
|---|---|
| `/download/mac` | the newest `.dmg` |
| `/download/mac/0.1.8` | that exact version |

So a new release changes where `/download/mac` points, and no page or README
link has to change.

```bash
pnpm sync-releases                 # refresh the list
pnpm build:ci                      # refresh, then build (what Cloudflare runs)
```

| Env | Meaning |
|---|---|
| `RELEASES_REPO` | `owner/name` to read releases from (default `cc-vb/dictator`) |
| `GITHUB_TOKEN` | needed once the repo is private |
| `DOWNLOAD_BASE` | where the `.dmg` files are served from. Unset, links point at GitHub release assets |
| `SITE_URL` | the public address, for canonical and share links |

If the release list cannot be fetched, the last committed `releases.json` is
kept, so a build never fails just because the network did.

## Deploy (Cloudflare Pages)

| Setting | Value |
|---|---|
| Root directory | `website` |
| Build command | `pnpm build:ci` |
| Output directory | `dist` |

Cloudflare builds and serves the site itself; nothing has to stay running on
anyone's machine.

## Layout

```
src/
  pages/        index, download (install guide), releases, 404
  components/   Hero, Sky (the painted backdrop), Features, HowItWorks,
                Platforms (the OS download cards), Faq, Nav, Footer
  styles/       global.css: colour, type and spacing tokens
  lib/          releases.ts: types and helpers over releases.json
scripts/        sync-releases.mjs
```
