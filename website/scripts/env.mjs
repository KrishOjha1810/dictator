// Loads the repo's root .env (the same file the release scripts read) into
// process.env. A variable already set wins, so Cloudflare Pages, which sets
// everything in its dashboard and has no .env, is unaffected.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const ROOT_ENV = fileURLToPath(new URL("../../.env", import.meta.url));

export function loadRootEnv() {
  let text;
  try {
    text = readFileSync(ROOT_ENV, "utf8");
  } catch {
    return;
  }
  for (const line of text.split("\n")) {
    const match = /^([A-Za-z0-9_]+)=(.*)$/.exec(line.trim());
    if (match && !process.env[match[1]]) process.env[match[1]] = match[2];
  }
}

// An address from the environment, without a trailing slash; "" when unset.
export function envUrl(name) {
  return (process.env[name] || "").trim().replace(/\/$/, "");
}
