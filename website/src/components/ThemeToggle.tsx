import "./ThemeToggle.css";

// The light and dark switch. index.html has already picked a theme before
// the first paint; this flips it and remembers the choice. It holds no React
// state, so the prerendered HTML is the same whichever theme is showing, and
// CSS shows the sun or the moon.
export default function ThemeToggle() {
  const flip = () => {
    const root = document.documentElement;
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch {
      // Private windows may refuse; the switch still works for this page.
    }
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", next === "dark" ? "#0f1b1c" : "#6e9f93");
  };

  return (
    <button type="button" className="c-theme" onClick={flip} aria-label="Switch light and dark">
      <svg className="sun" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </svg>
      <svg className="moon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />
      </svg>
    </button>
  );
}
