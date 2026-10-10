# Dictator website

The public site for Dictator: the landing page, the install guide, and the
download for each platform.

It is a [React](https://react.dev) site built with [Vite](https://vite.dev)
and prerendered: every page is written to `dist/` as finished HTML, then
React takes over in the browser for the parts that move (the demo in the
hero, the copy button). There is no server and no database; Cloudflare Pages
serves `dist/` as it is.

## Run it

```bash
cd website
pnpm install
pnpm dev            # http://localhost:5173
pnpm build && pnpm preview   # the built site, as it will be served
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
so an offline rebuild still works. Before the first release (no bucket
address, or nothing in the bucket yet) the site still builds, and every
download button says "Coming soon".

## Deploy (Cloudflare Pages)

The Pages project is connected to this repo and builds `main` with:

| Setting | Value |
|---|---|
| Root directory | `website` |
| Build command | `pnpm build` |
| Output directory | `dist` |
| Environment variables | `NODE_VERSION=24`, `PNPM_VERSION=12.5.1`, `DICTATOR_SITE_URL`, `DICTATOR_DOWNLOAD_BASE` |

Automatic deployments are off. `.github/workflows/website.yml` calls the
project's deploy hook after every app release and on a `website-*` tag on
`main`:

```bash
git tag website-2026-10-10 && git push origin website-2026-10-10
```

Cloudflare builds and serves the site; nothing has to stay running on
anyone's machine. Setup is in [`docs/cloudflare-r2.md`](../docs/cloudflare-r2.md).

## Layout

```
index.html      the page template every page is rendered into
src/
  main.tsx      the browser entry: hydrates the prerendered page
  entry-server.tsx  renders a page to HTML at build time
  App.tsx, routes.tsx  one page per address, with its title and description
  pages/        Home, Download (install guide), NotFound
  components/   Hero, Sky (the painted backdrop), Features, HowItWorks,
                Platforms (the OS download cards), Faq, Nav, Footer,
                PageHeader, DownloadButton. Each has its own .css, scoped
                under the class on its root element (.c-hero, .c-nav, ...)
  styles/       global.css: colour, type and spacing tokens
  lib/          latest.ts: types and helpers over latest.json
scripts/        sync-latest.mjs, prerender.mjs, env.mjs (loads the root .env)
```

`pnpm build` runs, in order: `sync-latest.mjs`, the browser build, the
server build of `entry-server.tsx`, and `prerender.mjs`, which writes
`index.html`, `download/index.html` and `404.html`.
