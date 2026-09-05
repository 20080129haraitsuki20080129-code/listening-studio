"use client";

import { useCallback, useSyncExternalStore } from "react";

import {
  type Locale,
  type MessageKey,
  messages,
} from "./messages";
import { getServerSnapshot, getSnapshot, setLocale, subscribe } from "./store";

export {
  LOCALES,
  LOCALE_NAMES,
  type Locale,
  type MessageKey,
} from "./messages";

export type Vars = Record<string, string | number>;

/** Substitute `{name}` placeholders. Missing vars are left visible on purpose. */
export function format(template: string, vars?: Vars): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match,
  );
}

export function useLocale(): Locale {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export function useTranslation() {
  const locale = useLocale();
  const t = useCallback(
    (key: MessageKey, vars?: Vars) => format(messages[locale][key], vars),
    [locale],
  );
  return { t, locale, setLocale };
}

/** Translate a value that comes from the API, falling back to the raw value. */
export function useDynamicLabel() {
  const locale = useLocale();
  return useCallback(
    (prefix: "accent" | "gender" | "render", value: string | null): string => {
      if (!value) return messages[locale]["accent.unknown"];
      const key = `${prefix}.${value}` as MessageKey;
      return messages[locale][key] ?? value;
    },
    [locale],
  );
}
