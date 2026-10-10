import { useEffect, useRef, type CSSProperties, type RefObject } from "react";
import Nav from "./Nav";
import Sky from "./Sky";
import DownloadButton from "./DownloadButton";
import { latest, macNeeds } from "../lib/latest";
import "./Hero.css";

type Scene = { app: string; where: string; context: string; said: string; lang: string };

// What the demo card plays, in order. Each one is a hold, a release, and the
// sentence landing in the app the cursor was in.
const scenes: Scene[] = [
  {
    app: "Slack",
    where: "#eng-backend",
    context: "anyone know why the export job takes 40s?",
    said: "yaar ye function thoda slow lag raha hai, can you check the loop",
    lang: "Hinglish",
  },
  {
    app: "Terminal",
    where: "zsh — ~/api",
    context: "$ git add -A",
    said: 'git commit -m "cache the invoice totals so the export stops timing out"',
    lang: "English",
  },
  {
    app: "Notes",
    where: "Standup",
    context: "Tuesday",
    said: "kal tak migration ho jayega, then we test on staging before Friday",
    lang: "Hinglish",
  },
];

// Plays the scenes in the demo card for as long as the page is open. It writes
// to the DOM directly rather than through React state: the card changes many
// times a second while typing, and nothing else on the page depends on it.
function useDemo(ref: RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const demo = ref.current;
    if (!demo) return;
    const $ = (sel: string) => demo.querySelector<HTMLElement>(sel)!;
    const state = $("[data-state]");
    const lang = $("[data-lang]");
    const app = $("[data-app]");
    const context = $("[data-context]");
    const said = $("[data-said]");
    const you = $("[data-you]");
    const chip = $("[data-chip]");
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

    let stopped = false;
    const wait = (ms: number) =>
      new Promise<void>((resolve, reject) => setTimeout(() => (stopped ? reject() : resolve()), ms));

    async function play(scene: Scene) {
      app.textContent = `${scene.app} — ${scene.where}`;
      context.textContent = scene.context;
      lang.textContent = scene.lang;
      said.textContent = "";
      you.classList.remove("shown");

      demo!.dataset.phase = "listening";
      state.textContent = "Listening…";
      chip.textContent = "Holding key";
      await wait(reduced ? 600 : 2600);

      demo!.dataset.phase = "working";
      state.textContent = "Transcribing";
      chip.textContent = "Released";
      await wait(reduced ? 200 : 700);

      demo!.dataset.phase = "pasted";
      state.textContent = "On device";
      chip.textContent = "Pasted ⏎";
      you.classList.add("shown");
      if (reduced) {
        said.textContent = scene.said;
      } else {
        // the paste is instant; the reveal is only paced so the eye can follow
        for (let i = 1; i <= scene.said.length; i += 3) {
          said.textContent = scene.said.slice(0, i);
          await wait(14);
        }
        said.textContent = scene.said;
      }
      await wait(reduced ? 4000 : 3400);
    }

    (async () => {
      for (let i = 0; ; i = (i + 1) % scenes.length) await play(scenes[i]);
    })().catch(() => {});
    return () => {
      stopped = true;
    };
  }, [ref]);
}

export default function Hero() {
  const demo = useRef<HTMLDivElement>(null);
  useDemo(demo);

  return (
    <section className="c-hero frame hero-frame">
      <div className="hero">
        <Sky />
        <div className="inner">
          <Nav />

          <div className="grid">
            <div className="copy">
              <h1>Talk. It types where your cursor is.</h1>
              <div className="lede">
                <p>
                  Hold your key, speak in English, Hindi or Hinglish, let go. Dictator writes it into any app
                  on your Mac, and no audio ever leaves it.
                </p>
                <div className="actions">
                  <DownloadButton>
                    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
                      <path
                        d="M8 1v9m0 0L4.5 6.5M8 10l3.5-3.5M2 13.5h12"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.6"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      ></path>
                    </svg>
                    Download for Mac
                  </DownloadButton>
                  <a className="btn btn-glass" href="#how">
                    See how it works
                  </a>
                </div>
                <p className="meta mono">
                  {latest ? `v${latest.version}` : "Coming soon"} · macOS {macNeeds.minOS}+ · {macNeeds.arch} · Free
                </p>
              </div>
            </div>

            <div className="demo" ref={demo}>
              <div className="status mono">
                <span className="dot-label">
                  <i className="dot"></i>
                  <span data-state="">Listening</span>
                </span>
                <span data-lang="">Hinglish</span>
              </div>
              <div className="card">
                <div className="chrome">
                  <span className="lights">
                    <i></i>
                    <i></i>
                    <i></i>
                  </span>
                  <span className="mono app" data-app="">
                    Slack — #eng-backend
                  </span>
                </div>
                <div className="thread">
                  <div className="bubble them">
                    <p data-context="">{scenes[0].context}</p>
                    <time className="mono">9:31 AM</time>
                  </div>
                  <div className="bubble you" data-you="">
                    <p>
                      <span data-said=""></span>
                      <i className="caret"></i>
                    </p>
                    <time className="mono">9:32 AM</time>
                  </div>
                </div>
                <div className="footer">
                  <div className="wave" aria-hidden="true">
                    {Array.from({ length: 22 }, (_, i) => (
                      <i key={i} style={{ "--i": i } as CSSProperties} />
                    ))}
                  </div>
                  <span className="chip" data-chip="">
                    Hold key
                  </span>
                </div>
              </div>
              <div className="badge">
                <img src="/icon.png" alt="" width={40} height={40} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
