import type { ComponentType } from "react";
import Home from "./pages/Home";
import Download from "./pages/Download";
import NotFound from "./pages/NotFound";

export interface Route {
  // Where the prerendered page is written in dist/, and the address it serves.
  file: string;
  title: string;
  description: string;
  Page: ComponentType;
}

export const routes: Record<string, Route> = {
  "/": {
    file: "index.html",
    title: "Dictator: voice typing for Mac",
    description:
      "Hold a key, talk, and the words land where your cursor is. English, Hindi and Hinglish, entirely on your Mac.",
    Page: Home,
  },
  "/download": {
    file: "download/index.html",
    title: "Download Dictator for Mac",
    description:
      "Download Dictator for macOS 14+ on Apple silicon, with step-by-step install instructions. iOS and Windows are coming soon.",
    Page: Download,
  },
  "/404": {
    // Cloudflare Pages serves 404.html for any address with no page.
    file: "404.html",
    title: "Page not found · Dictator",
    description: "This page does not exist.",
    Page: NotFound,
  },
};

export function routeFor(pathname: string): Route {
  const path = pathname.replace(/\/index\.html$/, "").replace(/\/+$/, "") || "/";
  return routes[path] ?? routes["/404"];
}
