import { renderToString } from "react-dom/server";
import App from "./App";
import { routes } from "./routes";

export { routes };

export function render(path: string): string {
  return renderToString(<App path={path} />);
}
