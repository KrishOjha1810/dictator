import { defineConfig } from "astro/config";

// SITE_URL is the public address once a domain exists. Until then the
// Cloudflare Pages subdomain stands in. It feeds canonical URLs and og tags.
export default defineConfig({
  site: process.env.SITE_URL || "https://dictator.pages.dev",
  output: "static",
  build: { format: "directory" },
});
