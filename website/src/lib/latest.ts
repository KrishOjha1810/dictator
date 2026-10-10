import data from "../data/latest.json";

export interface Latest {
  version: string;
  date: string;
  mac: {
    url: string;
    size: number;
    sha256: string;
    minOS: string;
    arch: string;
  };
}

export const latest: Latest = data;

// The stable address for the newest build. public/_redirects points it at the
// current file, so this link never changes between releases.
export const latestMacHref = "/download/mac";

export function formatSize(bytes: number): string {
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}
