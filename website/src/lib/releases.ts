import data from "../data/releases.json";

export interface MacBuild {
  file: string;
  url: string;
  size: number;
  sha256: string;
  minOS: string;
  arch: string;
}

export interface Release {
  version: string;
  date: string;
  notes: string;
  mac: MacBuild;
}

export const releases: Release[] = data.releases;
export const latest: Release = releases[0];

// The stable address for the newest build. public/_redirects points it at the
// current file, so this link never changes between releases.
export const latestMacHref = "/download/mac";
export const macHref = (version: string) => `/download/mac/${version}`;

export function formatSize(bytes: number): string {
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}
