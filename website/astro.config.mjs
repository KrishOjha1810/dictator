import { defineConfig } from "astro/config";
import { envUrl, loadRootEnv } from "./scripts/env.mjs";

loadRootEnv();

// The public address, for canonical and share links. DICTATOR_SITE_URL from
// the environment or the root .env; on Cloudflare Pages without it, the
// deployment's own address. Unset, pages are built without absolute links.
const site = envUrl("DICTATOR_SITE_URL") || envUrl("CF_PAGES_URL") || undefined;

export default defineConfig({
  site,
  output: "static",
  build: { format: "directory" },
});
