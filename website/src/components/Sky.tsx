import "./Sky.css";

// The painted backdrop behind the hero: a dusk sky with peach cloud streaks,
// soft teal hills, still water and a glowing key resting on it. All of it is
// CSS and inline SVG, so it costs no image download and scales to any width.

// Deterministic "random" so the meadow is identical on every build, and the
// same on the server and in the browser.
let seed = 7;
const rand = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;

const petals = Array.from({ length: 150 }, () => {
  const side = rand() < 0.62 ? "left" : "right";
  const x = side === "left" ? rand() * 34 : 78 + rand() * 22;
  const y = 52 + Math.pow(rand(), 0.7) * 46;
  const hue = rand();
  const color = hue < 0.45 ? "#f6c6cf" : hue < 0.7 ? "#fff3f1" : hue < 0.85 ? "#f4a9b7" : "#ffd9b8";
  const size = 2 + rand() * 4.5;
  return { x, y, color, size, o: 0.55 + rand() * 0.45 };
});

function OptionKey({ reflection = false }: { reflection?: boolean }) {
  return (
    <div className={reflection ? "key reflection" : "key"}>
      <span>⌥</span>
      <small>option</small>
    </div>
  );
}

export default function Sky() {
  return (
    <div className="c-sky sky" aria-hidden="true">
      <div className="cloud c1"></div>
      <div className="cloud c2"></div>
      <div className="cloud c3"></div>
      <div className="cloud c4"></div>

      <svg className="hills" viewBox="0 0 1600 600" preserveAspectRatio="none">
        <defs>
          <linearGradient id="hill-far" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#8cc4b4" />
            <stop offset="1" stopColor="#5f9f8e" />
          </linearGradient>
          <linearGradient id="hill-near" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#79b7a4" />
            <stop offset="1" stopColor="#4e8c7b" />
          </linearGradient>
          <linearGradient id="water" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#a9d3c9" />
            <stop offset="0.5" stopColor="#8dc2b6" />
            <stop offset="1" stopColor="#6aa797" />
          </linearGradient>
        </defs>
        <path
          d="M0 330 C 180 250 320 300 470 270 C 640 236 760 300 900 280 C 1080 254 1180 170 1330 190 C 1450 205 1520 250 1600 236 L1600 420 L0 420 Z"
          fill="url(#hill-far)"
          opacity="0.85"
        />
        <path
          d="M0 380 C 220 330 360 360 560 344 C 760 328 900 380 1100 356 C 1280 334 1420 300 1600 318 L1600 430 L0 430 Z"
          fill="url(#hill-near)"
          opacity="0.9"
        />
        <rect x="0" y="408" width="1600" height="192" fill="url(#water)" />
      </svg>

      <div className="ripples"></div>

      <div className="key-scene">
        <div className="glow"></div>
        <OptionKey />
        <OptionKey reflection />
      </div>

      <div className="meadow">
        {petals.map((p, i) => (
          <i
            key={i}
            style={{
              left: `${p.x.toFixed(2)}%`,
              top: `${p.y.toFixed(2)}%`,
              width: `${p.size.toFixed(1)}px`,
              height: `${p.size.toFixed(1)}px`,
              background: p.color,
              opacity: Number(p.o.toFixed(2)),
            }}
          />
        ))}
      </div>

      <div className="grain"></div>
      <div className="veil"></div>
    </div>
  );
}
