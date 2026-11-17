import { useEffect, useState } from 'react';

export type ThemeChoice = 'system' | 'light' | 'dark';

const KEY = 'automanga-theme';

function stored(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY);
    return v === 'light' || v === 'dark' ? v : 'system';
  } catch {
    return 'system';
  }
}

/** The theme choice, applied as html[data-theme] (index.html applies it before the first paint too).
    'system' removes the attribute, so the prefers-color-scheme rule in globals.css decides. */
export function useTheme() {
  const [theme, setTheme] = useState<ThemeChoice>(stored);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', theme);
    try {
      if (theme === 'system') localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, theme);
    } catch { /* private mode: the choice lasts for this visit */ }
  }, [theme]);

  return { theme, setTheme };
}
