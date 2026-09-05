"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { LanguageToggle } from "@/components/LanguageToggle";
import { SignOutButton } from "@/components/SignOutButton";
import { ApiError, api } from "@/lib/api";
import { type MessageKey, useTranslation } from "@/lib/i18n";
import type { ProjectSummary } from "@/lib/types";

export default function HomePage() {
  const { t, locale } = useTranslation();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setProjects(await api.listProjects());
    } catch (e) {
      if (e instanceof ApiError) {
        const key = `error.${e.code}` as MessageKey;
        const localized = t(key);
        setError(localized === key ? e.message : localized);
      } else {
        setError(t("projects.loadFailed"));
      }
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    // The setState calls inside load() run after an await, so they land in a
    // microtask rather than synchronously in the effect body.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const remove = async (id: string) => {
    await api.deleteProject(id);
    await load();
  };

  return (
    <main className="mx-auto max-w-3xl space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("app.title")}</h1>
        <div className="flex items-center gap-3">
          <LanguageToggle />
          <SignOutButton />
          <Link href="/create" className="btn-primary">
            {t("projects.new")}
          </Link>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
        >
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-slate-500">{t("projects.loading")}</p>
      ) : projects.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500 dark:border-slate-700">
          {t("projects.empty")}
        </p>
      ) : (
        <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-700">
          {projects.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-3 p-3">
              <Link href={`/projects/${p.id}`} className="flex-1">
                <div className="font-medium">{p.title}</div>
                <div className="text-xs text-slate-500 dark:text-slate-400">
                  {t("projects.updated", {
                    mode:
                      p.mode === "monologue"
                        ? t("mode.monologue")
                        : p.mode === "dialogue"
                          ? t("mode.dialogue")
                          : p.mode,
                    date: new Date(p.updated_at).toLocaleString(locale),
                  })}
                </div>
              </Link>
              <button onClick={() => remove(p.id)} className="chip">
                {t("projects.delete")}
              </button>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
