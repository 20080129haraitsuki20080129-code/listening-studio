"use client";

import { LOCALES, LOCALE_NAMES, useTranslation } from "@/lib/i18n";

export function LanguageToggle() {
  const { t, locale, setLocale } = useTranslation();

  return (
    <div
      role="group"
      aria-label={t("app.language")}
      className="inline-flex overflow-hidden rounded-full border border-slate-300 dark:border-slate-700"
    >
      {LOCALES.map((option) => (
        <button
          key={option}
          onClick={() => setLocale(option)}
          aria-pressed={locale === option}
          lang={option}
          className={`px-3 py-1 text-xs transition ${
            locale === option
              ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
              : "hover:bg-slate-100 dark:hover:bg-slate-800"
          }`}
        >
          {LOCALE_NAMES[option]}
        </button>
      ))}
    </div>
  );
}
