import { createRoot, hydrateRoot } from "react-dom/client";
import App from "./App";
import { routeFor } from "./routes";

const root = document.getElementById("root")!;
const app = <App path={location.pathname} />;

if (root.firstElementChild) {
  // A built page: the HTML is already there (scripts/prerender.mjs), and this
  // makes it live: the demo in the hero and the copy button.
  hydrateRoot(root, app);
} else {
  // `pnpm dev` serves the bare template, so render the page here.
  document.title = routeFor(location.pathname).title;
  createRoot(root).render(app);
}
