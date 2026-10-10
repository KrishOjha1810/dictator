#!/usr/bin/env node
// Writes every page as finished HTML, so the site works and is indexable
// before any JavaScript runs. Runs after `vite build` (the browser bundle in
// dist/) and the server build of src/entry-server.tsx (dist-server/).
//
// The template is dist/index.html, which Vite has already filled with the
// built CSS and script. Each page gets its own title, description and, when
// the site's address is known (DICTATOR_SITE_URL), canonical and share links.
// Not CF_PAGES_URL: on Cloudflare that is each build's own preview address.

import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { envUrl, loadRootEnv } from "./env.mjs";

loadRootEnv();

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const DIST = `${ROOT}dist/`;
const SERVER = `${ROOT}dist-server/entry-server.js`;
const SITE = envUrl("DICTATOR_SITE_URL");

const escape = (s) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

function head(path, { title, description }) {
  const canonical = SITE && path !== "/404" ? `${SITE}${path === "/" ? "/" : `${path}/`}` : "";
  const image = SITE ? `${SITE}/icon.png` : "/icon.png";
  return [
    `<title>${escape(title)}</title>`,
    `<meta name="description" content="${escape(description)}" />`,
    canonical && `<link rel="canonical" href="${canonical}" />`,
    `<meta property="og:type" content="website" />`,
    `<meta property="og:title" content="${escape(title)}" />`,
    `<meta property="og:description" content="${escape(description)}" />`,
    canonical && `<meta property="og:url" content="${canonical}" />`,
    `<meta property="og:image" content="${image}" />`,
  ]
    .filter(Boolean)
    .join("\n    ");
}

const template = await readFile(`${DIST}index.html`, "utf8");
const { render, routes } = await import(pathToFileURL(SERVER).href);

for (const [path, route] of Object.entries(routes)) {
  const html = template.replace("<!--app-head-->", head(path, route)).replace("<!--app-html-->", render(path));
  const out = `${DIST}${route.file}`;
  await mkdir(dirname(out), { recursive: true });
  await writeFile(out, html);
  console.log(`prerender: ${path} -> dist/${route.file}`);
}

await rm(`${ROOT}dist-server`, { recursive: true, force: true });
