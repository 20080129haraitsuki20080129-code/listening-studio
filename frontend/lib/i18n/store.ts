"use client";

import { LOCALES, type Locale } from "./messages";

const STORAGE_KEY = "listening-studio.locale";

/**
 * The chosen locale, held outside React so it can be read during render
 * without an effect.
 *
 * `null` means "not resolved yet"; it is resolved lazily on first read so the
 * module stays safe to import on the server.
 */
let current: Locale | null = null;
const listeners = new Set<() => void>();

function isLocale(value: unknown): value is Locale {
  return LOCALES.includes(value as Locale);
}

function detect(): Locale {
  // An explicit choice always wins over the browser's preference.
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isLocale(stored)) return stored;
  } catch {
    // Private mode or blocked storage; fall through to detection.
  }
  try {
    if (window.navigator.language?.toLowerCase().startsWith("ja")) return "ja";
  } catch {
    // No navigator (non-browser environment).
  }
  return "en";
}

export function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
  };
}

export function getSnapshot(): Locale {
  if (current === null) current = detect();
  return current;
}

/**
 * Server render always uses English. React swaps to the client snapshot right
 * after hydration, so a Japanese preference applies without a markup mismatch.
 */
export function getServerSnapshot(): Locale {
  return "en";
}

export function setLocale(locale: Locale): void {
  if (current === locale) return;
  current = locale;
  try {
    window.localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    // Preference simply will not persist; the session still switches.
  }
  for (const listener of listeners) listener();
}
