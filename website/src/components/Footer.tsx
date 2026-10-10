import DownloadButton from "./DownloadButton";
import { latest } from "../lib/latest";
import "./Footer.css";

export default function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="c-foot foot">
      <div className="cta">
        <h2>Stop typing what you could just say.</h2>
        <DownloadButton>Download for Mac</DownloadButton>
      </div>
      <div className="row">
        <a className="brand" href="/">
          <img src="/icon.png" alt="" width={28} height={28} />
          Dictator
        </a>
        <nav className="mono" aria-label="Footer">
          <a href="/download">Install guide</a>
          <a href="/#faq">FAQ</a>
        </nav>
        <p className="mono">
          {latest && `v${latest.version} · `}© {year}
        </p>
      </div>
    </footer>
  );
}
