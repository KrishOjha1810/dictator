import type { CSSProperties } from "react";
import "./Features.css";

const apps = ["Slack", "Terminal", "VS Code", "Chrome", "Notion", "Mail", "Messages", "Linear", "Figma", "Notes"];

const landed = [
  { app: "Slack", where: "#design-review", time: "Thu, 2:04 PM", initial: "S" },
  { app: "Terminal", where: "zsh — ~/api", time: "Thu, 3:31 PM", initial: ">" },
  { app: "Mail", where: "Re: launch plan", time: "Fri, 10:02 AM", initial: "M" },
];

const pills = [
  "Runs on device",
  "No audio uploaded",
  "No account",
  "Works offline",
  "Models SHA256-checked",
  "No subscription",
];

const keys = [
  { label: "right ⌥", note: "default", on: true },
  { label: "fn", note: "globe" },
  { label: "right ⌘", note: "" },
  { label: "left ⌘", note: "" },
];

export default function Features() {
  return (
    <section className="c-features frame" id="features">
      <div className="panel">
        <div className="strip">
          <p className="mono">Works in every text field on your Mac</p>
          <ul>
            {apps.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>

        <header className="section-head">
          <h2>The keyboard that keeps up with how you talk</h2>
          <p>From the moment you hold the key to the moment the words land, Dictator handles the whole sentence.</p>
        </header>

        <div className="bento">
          <article className="tile green">
            <h3>Every app, every field. No plugins.</h3>
            <ul className="stack">
              {landed.map((l) => (
                <li key={l.app}>
                  <span className="avatar">{l.initial}</span>
                  <span className="when">{l.time}</span>
                  <strong>{l.app}</strong>
                  <span className="chip">Pasted</span>
                </li>
              ))}
            </ul>
          </article>

          <article className="tile mint">
            <div className="marquee" aria-hidden="true">
              {[0, 1, 2].map((row) => {
                const order = [...pills.slice(row * 2), ...pills.slice(0, row * 2)];
                return (
                  <div
                    key={row}
                    className="row"
                    style={{ "--dir": row % 2 ? "reverse" : "normal", "--dur": `${28 + row * 6}s` } as CSSProperties}
                  >
                    {[...order, ...order].map((p, i) => (
                      <span key={i} style={{ "--o": (i + row) % 3 === 0 ? 1 : 0.7 } as CSSProperties}>
                        {p}
                      </span>
                    ))}
                  </div>
                );
              })}
            </div>
            <ul className="visually-hidden">
              {pills.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
            <h3 className="big">Private by default</h3>
          </article>

          <article className="tile scene">
            <div className="mini-sky" aria-hidden="true"></div>
            <div className="keys-card">
              <div className="keys">
                {keys.map((k) => (
                  <span key={k.label} className={k.on ? "k on" : "k"}>
                    {k.label}
                    {k.note && <small>{k.note}</small>}
                  </span>
                ))}
              </div>
              <p className="cap">Hold to talk. Double-tap for hands free.</p>
            </div>
          </article>
        </div>
      </div>
    </section>
  );
}
