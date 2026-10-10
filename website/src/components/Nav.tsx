import DownloadButton from "./DownloadButton";
import ThemeToggle from "./ThemeToggle";
import "./Nav.css";

const links = [
  { href: "/#how", label: "How it works" },
  { href: "/#features", label: "Features" },
  { href: "/download", label: "Install" },
];

// On the sky hero the nav is white glass; on a light panel it is ink.
export default function Nav({ tone = "sky" }: { tone?: "sky" | "panel" }) {
  return (
    <header className={`c-nav nav ${tone}`}>
      <a className="brand" href="/" aria-label="Dictator home">
        <img src="/icon.png" alt="" width={34} height={34} />
        <span>Dictator</span>
      </a>
      <nav className="links" aria-label="Main">
        {links.map((l) => (
          <a key={l.href} className="mono" href={l.href}>
            {l.label}
          </a>
        ))}
        <ThemeToggle />
        <DownloadButton className="btn btn-dark cta">Download</DownloadButton>
      </nav>
    </header>
  );
}
