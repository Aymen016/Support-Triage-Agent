import { useEffect, useState } from "react";

type Theme = "light" | "dark";

function initialTheme(): Theme {
  // index.html already set this synchronously before first paint —
  // this just reads that same decision into React state.
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("theme", theme);
    } catch {
      // per-viewer convenience only — fine if storage is unavailable
    }
  }, [theme]);

  function toggle() {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }

  return [theme, toggle];
}
