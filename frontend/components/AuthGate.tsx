"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, api, loginUrl } from "@/lib/api";
import { type MessageKey, useTranslation } from "@/lib/i18n";
import type { AuthStatus } from "@/lib/types";

/**
 * Shows the sign-in screen until there is a session.
 *
 * When the server has no identity provider configured it cannot require
 * sign-in -- there would be no way in -- so the app is shown as-is with a
 * standing warning that the instance is open.
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus(await api.authStatus());
    } catch (e) {
      setError(
        e instanceof ApiError ? t(`error.${e.code}` as MessageKey) : t("error.generic"),
      );
    }
  }, [t]);

  useEffect(() => {
    // setState runs after an await, so it lands in a microtask rather than
    // synchronously in the effect body.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  if (error) {
    return (
      <main className="mx-auto max-w-md p-6">
        <div
          role="alert"
          className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
        >
          {error}
        </div>
      </main>
    );
  }

  if (!status) {
    return (
      <main className="mx-auto max-w-md p-6 text-sm text-slate-500">
        {t("auth.checking")}
      </main>
    );
  }

  if (status.auth_required && !status.authenticated) {
    return <SignIn providers={status.providers} />;
  }

  return (
    <>
      {!status.auth_required && (
        <div className="border-b border-amber-300 bg-amber-50 px-4 py-2 text-center text-xs text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          {t("auth.noProviders")}
        </div>
      )}
      {children}
    </>
  );
}

function SignIn({ providers }: { providers: string[] }) {
  const { t } = useTranslation();
  return (
    <main className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center gap-4 p-6">
      <h1 className="text-xl font-semibold">{t("auth.signInTitle")}</h1>
      <p className="text-sm text-slate-500 dark:text-slate-400">
        {t("auth.signInBlurb")}
      </p>
      <div className="space-y-2">
        {providers.includes("google") && (
          <a href={loginUrl("google")} className="btn-primary block text-center">
            {t("auth.withGoogle")}
          </a>
        )}
        {providers.includes("x") && (
          <a href={loginUrl("x")} className="btn-primary block text-center">
            {t("auth.withX")}
          </a>
        )}
      </div>
    </main>
  );
}
