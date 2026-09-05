"use client";

import { useEffect } from "react";

import { useLocale } from "@/lib/i18n";

/**
 * Keep `<html lang>` in step with the chosen locale.
 *
 * The document element is outside React's tree, and screen readers and browser
 * translation both key off this attribute.
 */
export function HtmlLangSync() {
  const locale = useLocale();
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  return null;
}
