import { latest, formatSize } from "../lib/latest";
import "./Faq.css";

const appSize = latest ? `about ${formatSize(latest.mac.size)}` : "small";

const faqs = [
  {
    q: "Is it free?",
    a: "Yes. There is no account, no trial and no subscription.",
  },
  {
    q: "Does my voice leave my Mac?",
    a: "No. Speech is recognised by models that run on your Mac. The only downloads are the models themselves on first launch and app updates, and each model is checked against its published SHA256 before it is used.",
  },
  {
    q: "Why does macOS warn me when I first open it?",
    a: "Dictator is not paid into Apple's developer programme, so macOS stops it the first time. Press Done, then open System Settings → Privacy & Security and press Open Anyway next to Dictator. This happens once. The install guide walks through it.",
  },
  {
    q: "Which Macs does it run on?",
    a: "Macs with Apple silicon (M1 or newer) on macOS 14 Sonoma or later. iOS and Windows versions are coming.",
  },
  {
    q: "How much space does it need?",
    a: `The app is ${appSize}. On first launch it downloads the English model (about 700 MB), then the Hindi and Hinglish models in the background (about 1.5 GB).`,
  },
  {
    q: "How do updates work?",
    a: "Installed copies check for new versions and update themselves. You can also choose Check for Updates from the menu bar. The download button on this site always gives you the newest version.",
  },
  {
    q: "Which key do I hold?",
    a: "Right ⌥ Option, unless you change it. You can also pick fn (🌐), right ⌘ or left ⌘. Double-tap the key for hands free dictation.",
  },
];

export default function Faq() {
  return (
    <section className="c-faq frame" id="faq">
      <div className="panel">
        <div className="wrap">
          <header>
            <span className="eyebrow">Questions</span>
            <h2>Good to know</h2>
          </header>
          <div className="list">
            {faqs.map((f, i) => (
              <details key={f.q} open={i === 0}>
                <summary>
                  {f.q}
                  <span className="plus" aria-hidden="true" />
                </summary>
                <p>{f.a}</p>
              </details>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
