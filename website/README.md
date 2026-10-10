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

## Configuration

Nothing about where the site or the downloads live is written in the code.
Every address comes from the environment, or locally from the repo's root
`.env` (never committed; `../.env.example` lists every name). A variable set
in the environment wins over `.env`.

| Variable | Meaning |
|---|---|
| `DICTATOR_SITE_URL` | the site's public address, for canonical and share links. On Cloudflare Pages without it, the deployment's own address is used |
| `DICTATOR_DOWNLOAD_BASE` | the R2 bucket's public URL, required. The release comes from its `latest.json`, and `/download/mac` and `/appcast.xml` redirect into it. See [`docs/cloudflare-r2.md`](../docs/cloudflare-r2.md) |

## Where the version number comes from

The site offers one download per platform: the newest build. Every build runs
`scripts/sync-latest.mjs` first, which writes two files that are generated,
not committed:

| File | What it holds |
|---|---|
| `src/data/latest.json` | version, date, size, SHA256, minimum macOS |
| `public/_redirects` | `/download/mac` and `/appcast.xml` |

Every download button links to `/download/mac`, never to a file host, so a
release changes where that link points and no page has to change.

```bash
pnpm dev                           # sync, then the dev server
pnpm build                         # sync, then build (what Cloudflare runs)
```

If the release cannot be fetched, a `latest.json` from an earlier run is kept,
so an offline rebuild still works. The very first build needs a release in
the bucket.

## Deploy (Cloudflare Pages)

| Setting | Value |
|---|---|
| Root directory | `website` |
| Build command | `pnpm build` |
| Output directory | `dist` |
| Environment variables | `NODE_VERSION=22`, plus the variables above |

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
scripts/        sync-latest.mjs, env.mjs (loads the root .env)
```
