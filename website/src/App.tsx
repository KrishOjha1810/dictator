import Footer from "./components/Footer";
import { routeFor } from "./routes";
import "./styles/global.css";

// One page per address, picked by its path. The pages are plain links to each
// other, so every page is a full load of its own prerendered HTML.
export default function App({ path }: { path: string }) {
  const { Page } = routeFor(path);
  return (
    <div className="page">
      <Page />
      <Footer />
    </div>
  );
}
