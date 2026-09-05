"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { useTranslation } from "@/lib/i18n";
import type { CurrentUser } from "@/lib/types";

export function SignOutButton() {
  const { t } = useTranslation();
  const [user, setUser] = useState<CurrentUser | null>(null);

  const load = useCallback(async () => {
    try {
      setUser((await api.authStatus()).user);
    } catch {
      // The gate already reports a failure; the header just stays quiet.
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  if (!user) return null;

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-slate-500 dark:text-slate-400">
        {user.display_name}
      </span>
      <button
        onClick={async () => {
          await api.logout();
          window.location.reload();
        }}
        className="chip"
      >
        {t("auth.signOut")}
      </button>
    </div>
  );
}
