import { useState } from "react";
import DownloadButton from "./DownloadButton";
import { latest, macNeeds, formatSize, formatDate } from "../lib/latest";
import "./Platforms.css";

const soon = [
  {
    os: "iOS",
    title: "iPhone & iPad",
    body: "Dictate into any app from the keyboard, with the same on-device models.",
    icon: "phone",
  },
  {
    os: "Windows",
    title: "Windows 11",
    body: "Hold a key and talk, in every Windows app. Same Hinglish engine.",
    icon: "windows",
  },
];

function CopyButton({ text }: { text: string }) {
  const [label, setLabel] = useState("Copy");
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setLabel("Copied");
    } catch {
      setLabel("Select it");
    }
    setTimeout(() => setLabel("Copy"), 1600);
  }
  return (
    <button type="button" className="copy mono" onClick={copy}>
      {label}
    </button>
  );
}

export default function Platforms({
  heading = "Download Dictator",
  intro = "Free. Runs entirely on your Mac. Installed copies update themselves.",
}: {
  heading?: string;
  intro?: string;
}) {
  return (
    <section className="c-platforms frame" id="download">
      <div className="panel">
        <header className="section-head">
          <span className="eyebrow">Download</span>
          <h2>{heading}</h2>
          <p>{intro}</p>
        </header>

        <div className="platforms">
          <article className="mac">
            <div className="top">
              <span className="os">
                <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    fill="currentColor"
                    d="M16.4 12.6c0-2.4 2-3.6 2.1-3.7-1.1-1.7-2.9-1.9-3.5-1.9-1.5-.2-2.9.9-3.7.9-.8 0-1.9-.9-3.2-.8-1.6 0-3.1 1-4 2.4-1.7 3-.4 7.4 1.2 9.8.8 1.2 1.8 2.5 3 2.4 1.2 0 1.7-.8 3.1-.8 1.5 0 1.9.8 3.2.8 1.3 0 2.2-1.2 3-2.4.9-1.4 1.3-2.7 1.3-2.8 0 0-2.5-1-2.5-3.9ZM14 5.4c.7-.8 1.1-1.9 1-3-1 0-2.1.7-2.8 1.5-.6.7-1.2 1.8-1 2.9 1.1.1 2.1-.6 2.8-1.4Z"
                  ></path>
                </svg>
                macOS
              </span>
              {latest ? (
                <span className="chip live">
                  <i></i>Available
                </span>
              ) : (
                <span className="chip">Coming soon</span>
              )}
            </div>

            <h3>Dictator for Mac</h3>
            <dl className="facts">
              {latest && (
                <div>
                  <dt className="mono">Version</dt>
                  <dd>{latest.version}</dd>
                </div>
              )}
              {latest && (
                <div>
                  <dt className="mono">Released</dt>
                  <dd>{formatDate(latest.date)}</dd>
                </div>
              )}
              {latest && (
                <div>
                  <dt className="mono">Size</dt>
                  <dd>{formatSize(latest.mac.size)}</dd>
                </div>
              )}
              <div>
                <dt className="mono">Needs</dt>
                <dd>
                  macOS {macNeeds.minOS}+, {macNeeds.arch}
                </dd>
              </div>
            </dl>

            {latest && (
              <div className="sha">
                <span className="mono">SHA256</span>
                <code title={latest.mac.sha256}>{latest.mac.sha256}</code>
                <CopyButton text={latest.mac.sha256} />
              </div>
            )}

            <div className="actions">
              <DownloadButton>Download .dmg</DownloadButton>
              <a className="btn btn-soft" href="/download#install">
                Install guide
              </a>
            </div>
          </article>

          {soon.map((p) => (
            <article key={p.os} className="soon">
              <div className="top">
                <span className="os">
                  {p.icon === "phone" ? (
                    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
                      <rect x="6" y="2" width="12" height="20" rx="3" fill="none" stroke="currentColor" strokeWidth="1.8" />
                      <path d="M10.5 18.5h3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                    </svg>
                  ) : (
                    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
                      <path
                        fill="currentColor"
                        d="M3 5.5 10.5 4.4v7.1H3V5.5Zm8.5-1.2L21 3v8.5h-9.5V4.3ZM3 12.5h7.5v7.1L3 18.5v-6Zm8.5 0H21V21l-9.5-1.3v-7.2Z"
                      />
                    </svg>
                  )}
                  {p.os}
                </span>
                <span className="chip">Coming soon</span>
              </div>
              <h3>{p.title}</h3>
              <p>{p.body}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
