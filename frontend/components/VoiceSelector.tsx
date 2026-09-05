"use client";

import { useMemo, useState } from "react";

import type { Voice } from "@/lib/types";

type Props = {
  voices: Voice[];
  selectedId: string | null;
  onSelect: (voiceId: string) => void;
};

const ACCENT_LABELS: Record<string, string> = {
  american: "American",
  british: "British",
  australian: "Australian",
  canadian: "Canadian",
  irish: "Irish",
  indian: "Indian",
  scottish: "Scottish",
  new_zealand: "New Zealand",
  south_african: "South African",
  singaporean: "Singaporean",
  unknown: "Unknown",
};

function label(accent: string | null): string {
  if (!accent) return "Unknown";
  return ACCENT_LABELS[accent] ?? accent;
}

export function VoiceSelector({ voices, selectedId, onSelect }: Props) {
  const [accent, setAccent] = useState("");
  const [gender, setGender] = useState("");
  const [provider, setProvider] = useState("");
  const [query, setQuery] = useState("");

  const options = useMemo(() => {
    const uniq = (values: (string | null)[]) =>
      [...new Set(values.filter((v): v is string => Boolean(v)))].sort();
    return {
      accents: uniq(voices.map((v) => v.accent)),
      genders: uniq(voices.map((v) => v.gender)),
      providers: uniq(voices.map((v) => v.provider)),
    };
  }, [voices]);

  // Filtering happens client-side so it stays instant (SPEC section 25).
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return voices.filter(
      (v) =>
        (!accent || v.accent === accent) &&
        (!gender || v.gender === gender) &&
        (!provider || v.provider === provider) &&
        (!needle || v.name.toLowerCase().includes(needle)),
    );
  }, [voices, accent, gender, provider, query]);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <select
          value={accent}
          onChange={(e) => setAccent(e.target.value)}
          aria-label="Accent"
          className="field"
        >
          <option value="">All accents</option>
          {options.accents.map((a) => (
            <option key={a} value={a}>
              {label(a)}
            </option>
          ))}
        </select>

        <select
          value={gender}
          onChange={(e) => setGender(e.target.value)}
          aria-label="Gender"
          className="field"
        >
          <option value="">All genders</option>
          {options.genders.map((g) => (
            <option key={g} value={g}>
              {g[0].toUpperCase() + g.slice(1)}
            </option>
          ))}
        </select>

        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          aria-label="Provider"
          className="field"
        >
          <option value="">All providers</option>
          {options.providers.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>

        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search name"
          aria-label="Search voices"
          className="field"
        />
      </div>

      <p className="text-xs text-slate-500 dark:text-slate-400">
        {filtered.length} of {voices.length} voices
      </p>

      <ul className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
        {filtered.map((voice) => {
          const selected = voice.id === selectedId;
          return (
            <li key={voice.id}>
              <button
                onClick={() => onSelect(voice.id)}
                aria-pressed={selected}
                className={`w-full rounded-md border px-3 py-2 text-left text-sm transition ${
                  selected
                    ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                    : "border-slate-200 hover:border-slate-400 dark:border-slate-700 dark:hover:border-slate-500"
                }`}
              >
                <div className="font-medium">{voice.name}</div>
                <div
                  className={`text-xs ${selected ? "opacity-80" : "text-slate-500 dark:text-slate-400"}`}
                >
                  {label(voice.accent)} · {voice.gender} · {voice.provider}
                </div>
              </button>
            </li>
          );
        })}
        {filtered.length === 0 && (
          <li className="rounded border border-dashed border-slate-300 p-4 text-center text-sm text-slate-500 dark:border-slate-700">
            No voices match these filters.
          </li>
        )}
      </ul>
    </div>
  );
}
