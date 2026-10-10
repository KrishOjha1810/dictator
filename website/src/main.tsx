import { hydrateRoot } from "react-dom/client";
import App from "./App";

// The HTML is already there (scripts/prerender.mjs); this makes it live: the
// demo in the hero and the copy button.
hydrateRoot(document.getElementById("root")!, <App path={location.pathname} />);
