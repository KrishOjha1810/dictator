import data from "../data/latest.json";

export interface Latest {
  version: string;
  date: string;
  mac: {
    file: string;
    url: string;
    size: number;
    sha256: string;
    minOS: string;
    arch: string;
  };
}

// null until the first release reaches the bucket: the site still builds, and
// every download button says "Coming soon" instead.
export const latest = data as Latest | null;

// What the Mac build needs, for the pages to say before there is a release.
export const macNeeds = {
  minOS: (latest?.mac.minOS ?? "14.0").replace(/\.0$/, ""),
  arch: latest?.mac.arch ?? "Apple silicon",
};

// The stable address for the newest build. public/_redirects points it at the
// current file, so this link never changes between releases.
export const latestMacHref = "/download/mac";

export function formatSize(bytes: number): string {
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}
