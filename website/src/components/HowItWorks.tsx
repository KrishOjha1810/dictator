import "./HowItWorks.css";

const steps = [
  {
    n: "01",
    title: "Hold the key",
    body: "The key you choose, in any app. A small pill appears, and its bars move with your voice, so you always know the microphone is really open.",
  },
  {
    n: "02",
    title: "Say it the way you would",
    body: "English, Hindi, or both in one sentence. Code names, commands and half-English sentences come out the way you would type them.",
  },
  {
    n: "03",
    title: "Let go",
    body: "The sentence is transcribed on your Mac and pasted where your cursor is. Double-tap the key to keep talking hands free.",
  },
];

const tools = [
  { key: "⌥M", title: "Notetaker", body: "Records a meeting and gives you notes from it. It asks before it records anyone." },
  { key: "⌥S", title: "Scratchpad", body: "A notes window with the cursor ready. Notes are plain Markdown files on your Mac." },
  { key: "“…”", title: "Snippets", body: "Say “my work email” and the address lands. Phrases you say often, typed for you." },
  { key: "find", title: "Search everything you said", body: "Find a sentence by what landed or by what it misheard, filtered by app or by day." },
];

export default function HowItWorks() {
  return (
    <section className="c-how frame" id="how">
      <div className="panel">
        <header className="section-head">
          <span className="eyebrow">How it works</span>
          <h2>Hold. Talk. Let go.</h2>
          <p>No window to switch to and no button to click. The words go where you were already typing.</p>
        </header>

        <ol className="steps">
          {steps.map((s) => (
            <li key={s.n}>
              <span className="n mono">{s.n}</span>
              <h3>{s.title}</h3>
              <p>{s.body}</p>
            </li>
          ))}
        </ol>

        <div className="lang">
          <div className="lang-copy">
            <span className="eyebrow">Built for Hinglish</span>
            <h3>Spoken in two languages. Written in one script.</h3>
            <p>
              Most dictation gives you mangled English or Devanagari you can't paste into a terminal. Dictator writes
              mixed Hindi and English in Latin script, the way people actually type it.
            </p>
            <p className="note mono">Hinglish accuracy is still improving with every release.</p>
          </div>
          <div className="lang-demo" aria-label="Example">
            <div className="said">
              <span className="mono">You say</span>
              <p>“yaar ye function thoda slow lag raha hai, can you check the loop”</p>
            </div>
            <div className="arrow" aria-hidden="true">
              ↓
            </div>
            <div className="typed">
              <span className="mono">Dictator types</span>
              <p>
                yaar ye function thoda slow lag raha hai, can you check the loop<i className="caret"></i>
              </p>
            </div>
            <div className="langs">
              <span className="chip">English</span>
              <span className="chip">Hindi</span>
              <span className="chip">Hinglish</span>
            </div>
          </div>
        </div>

        <ul className="tools">
          {tools.map((t) => (
            <li key={t.title}>
              <span className="key">{t.key}</span>
              <h4>{t.title}</h4>
              <p>{t.body}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
