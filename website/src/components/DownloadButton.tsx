import type { ReactNode } from "react";
import { latest, latestMacHref } from "../lib/latest";

// The Mac download button. Before the first release it is the same button,
// greyed out, saying "Coming soon".
export default function DownloadButton({
  className = "btn btn-dark",
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  if (!latest) {
    return (
      <span className={className} aria-disabled="true">
        Coming soon
      </span>
    );
  }
  return (
    <a className={className} href={latestMacHref} data-download="">
      {children}
    </a>
  );
}
