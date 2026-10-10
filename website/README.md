# Dictator website

The public site for Dictator: the landing page, the install guide, and the
download for each platform.

It is a static [Astro](https://astro.build) site. There is no server and no
database; the build writes plain HTML to `dist/`, which Cloudflare Pages
serves.

## Run it

```bash
cd website
pnpm install
pnpm dev            # http://localhost:4321
```

## Where the version number comes from

The site offers one download per platform: the newest build. There is no
version history on the site.

`scripts/sync-latest.mjs` reads the newest release and writes:

| File | What it holds |
|---|---|
| `src/data/latest.json` | version, date, size, SHA256, minimum macOS |
| `public/_redirects` | `/download/mac`, pointed at the newest `Dictator.dmg` |

Every download button links to `/download/mac`, never to a file host directly,
so a new release changes where that link points and no page has to change.

```bash
pnpm sync-latest                   # refresh latest.json and _redirects
pnpm build:ci                      # refresh, then build (what Cloudflare runs)
```

| Env | Meaning |
|---|---|
| `RELEASES_REPO` | `owner/name` to read the latest release from (default `cc-vb/dictator`) |
| `GITHUB_TOKEN` | needed once the repo is private |
| `DOWNLOAD_BASE` | where `Dictator.dmg` is served from. Unset, the link points at the GitHub release asset |
| `SITE_URL` | the public address, for canonical and share links |

If the release cannot be fetched, the last committed `latest.json` is kept, so
a build never fails just because the network did.

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
  pages/        index, download (install guide), 404
  components/   Hero, Sky (the painted backdrop), Features, HowItWorks,
                Platforms (the OS download cards), Faq, Nav, Footer
  styles/       global.css: colour, type and spacing tokens
  lib/          latest.ts: types and helpers over latest.json
scripts/        sync-latest.mjs
```
