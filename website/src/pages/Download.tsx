import PageHeader from "../components/PageHeader";
import Platforms from "../components/Platforms";
import DownloadButton from "../components/DownloadButton";
import { latest } from "../lib/latest";
import "./Download.css";

const steps = [
  {
    title: "Drag Dictator into Applications",
    body: "Open the .dmg and drag Dictator into Applications. Open it from Applications, not from the disk image window: macOS stops a copy run from the disk image after a few seconds. If you do open that one, it offers to move itself.",
  },
  {
    title: "Press Done when macOS stops it",
    body: "Dictator is free and not paid into Apple's developer programme, so macOS blocks the first launch. Press Done, not Move to Trash.",
  },
  {
    title: "Open Anyway, once",
    body: "Open System Settings → Privacy & Security, scroll down and press Open Anyway next to Dictator. Confirm. This happens only the first time.",
  },
  {
    title: "Allow the microphone and Accessibility",
    body: "Dictator asks for both. The microphone is for hearing you; Accessibility is what lets it paste into other apps. The speech models then download: English first (about 700 MB), then Hindi and Hinglish in the background (about 1.5 GB). Each is checked against its SHA256 before use.",
  },
  {
    title: "Hold right ⌥ and talk",
    body: "That's the key unless you change it. Double-tap it for hands free. If you switch to fn, set System Settings → Keyboard → Press 🌐 key to → Do Nothing, so macOS doesn't open the emoji picker on a tap.",
  },
];

export default function Download() {
  return (
    <>
      <PageHeader
        eyebrow="Install"
        title="Up and running in two minutes"
        intro={`Dictator ${latest ? `${latest.version} ` : ""}for macOS 14 or newer on Apple silicon. Free, with no account.`}
      >
        <div className="hero-actions">
          <DownloadButton>Download .dmg</DownloadButton>
          <a className="btn btn-glass" href="#install">
            Install guide
          </a>
        </div>
      </PageHeader>

      <section className="c-install frame" id="install">
        <div className="panel">
          <header className="section-head">
            <span className="eyebrow">Install guide</span>
            <h2>Five steps, once</h2>
            <p>macOS asks a few questions the first time. After that, Dictator updates itself.</p>
          </header>
          <ol className="steps">
            {steps.map((s, i) => (
              <li key={s.title}>
                <span className="n mono">{String(i + 1).padStart(2, "0")}</span>
                <div>
                  <h3>{s.title}</h3>
                  <p>{s.body}</p>
                </div>
              </li>
            ))}
          </ol>

          <div className="verify">
            <div>
              <h3>Check the download</h3>
              <p>The SHA256 printed next to every version should match what this prints:</p>
            </div>
            <pre>
              <code>shasum -a 256 ~/Downloads/{latest?.mac.file ?? "Dictator-<version>.dmg"}</code>
            </pre>
          </div>
        </div>
      </section>

      <Platforms heading="Every platform" intro="macOS is available now. iOS and Windows are on the way." />
    </>
  );
}
