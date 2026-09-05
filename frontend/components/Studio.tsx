"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { LanguageToggle } from "@/components/LanguageToggle";
import { ListeningPlayer } from "@/components/ListeningPlayer";
import { VoiceSelector } from "@/components/VoiceSelector";
import { ApiError, api } from "@/lib/api";
import { type MessageKey, useDynamicLabel, useTranslation } from "@/lib/i18n";
import type { Mode, Project, RenderJob, Voice } from "@/lib/types";

const SAMPLE_DIALOGUE = `[A]
Have you finished the report? Dr. Chen asked for it by 3.30 p.m.

[B]
Not yet. I found something interesting in the U.S. data.

[A]
What did you find?`;

const SAMPLE_MONOLOGUE = `Climate change is altering migration patterns across the world. Researchers say the shift is accelerating, and that some species are moving toward the poles faster than models predicted.`;

export function Studio({ projectId }: { projectId?: string }) {
  const { t } = useTranslation();
  const label = useDynamicLabel();
  const [project, setProject] = useState<Project | null>(null);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [title, setTitle] = useState("");
  const [mode, setMode] = useState<Mode>("monologue");
  const [sourceText, setSourceText] = useState(SAMPLE_MONOLOGUE);
  const [speed, setSpeed] = useState(1.0);
  const [transcriptVisible, setTranscriptVisible] = useState(true);

  const [job, setJob] = useState<RenderJob | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fail = useCallback(
    (e: unknown) => {
      if (!(e instanceof ApiError)) {
        setError(t("error.generic"));
        return;
      }
      const key = `error.${e.code}` as MessageKey;
      const localized = t(key);
      // t() returns the key unchanged when the code has no translation, in
      // which case the server's English message is more useful than the key.
      setError(localized === key ? e.message : localized);
    },
    [t],
  );

  const loadVoices = useCallback(async () => {
    try {
      let { items } = await api.listVoices({ enabled: "true" });
      // First run: the catalog is empty until the providers are imported.
      if (items.length === 0) {
        await api.syncVoices();
        items = (await api.listVoices({ enabled: "true" })).items;
      }
      setVoices(items);
    } catch (e) {
      fail(e);
    }
  }, [fail]);

  const loadProject = useCallback(
    async (id: string) => {
      try {
        const p = await api.getProject(id);
        setProject(p);
        setTitle(p.title);
        setMode(p.mode);
        setSourceText(p.source_text);
        setSpeed(Number(p.default_generation_speed));
        setTranscriptVisible(p.transcript_visible_default);
      } catch (e) {
        fail(e);
      }
    },
    [fail],
  );

  useEffect(() => {
    // setState runs after an await inside loadVoices(), so it lands in a
    // microtask rather than synchronously in the effect body.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadVoices();
  }, [loadVoices]);

  useEffect(() => {
    // Same reason as above.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (projectId) void loadProject(projectId);
  }, [projectId, loadProject]);

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
  }, []);

  const saveAndParse = useCallback(async () => {
    setError(null);
    setBusy("Saving");
    try {
      const effectiveTitle = title.trim() || t("editor.untitled");
      let current = project;
      if (!current) {
        current = await api.createProject({
          title: effectiveTitle,
          mode,
          source_text: sourceText,
        });
        window.history.replaceState(null, "", `/projects/${current.id}`);
      }
      await api.updateProject(current.id, {
        title: effectiveTitle,
        mode,
        default_generation_speed: speed,
        transcript_visible_default: transcriptVisible,
      });
      await api.parseProject(current.id, { source_text: sourceText, mode });
      await loadProject(current.id);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(null);
    }
  }, [project, title, mode, sourceText, speed, transcriptVisible, loadProject, fail, t]);

  const assignVoice = useCallback(
    async (speakerId: string, voiceId: string) => {
      if (!project) return;
      try {
        await api.updateSpeaker(speakerId, { voice_id: voiceId });
        await loadProject(project.id);
      } catch (e) {
        fail(e);
      }
    },
    [project, loadProject, fail],
  );

  const setDefaultVoice = useCallback(
    async (voiceId: string) => {
      if (!project) return;
      try {
        await api.updateProject(project.id, { default_voice_id: voiceId });
        await loadProject(project.id);
      } catch (e) {
        fail(e);
      }
    },
    [project, loadProject, fail],
  );

  const generate = useCallback(async () => {
    if (!project) return;
    setError(null);
    setBusy("Generating");
    try {
      const started = await api.createRender(project.id, "mp3");
      setJob(started);

      // Polling is enough for the MVP (SPEC section 20). The UI stays
      // responsive throughout; nothing blocks on the render.
      pollRef.current = setInterval(async () => {
        try {
          const current = await api.getRender(started.id);
          setJob(current);
          if (["completed", "failed", "cancelled"].includes(current.status)) {
            if (pollRef.current) clearInterval(pollRef.current);
            setBusy(null);
            if (current.status === "failed" && current.error) {
              setError(`${current.error.code}: ${current.error.message}`);
            } else if (current.status === "completed") {
              await loadProject(project.id);
            }
          }
        } catch (e) {
          if (pollRef.current) clearInterval(pollRef.current);
          setBusy(null);
          fail(e);
        }
      }, 700);
    } catch (e) {
      setBusy(null);
      fail(e);
    }
  }, [project, loadProject, fail]);

  const needsVoice =
    project &&
    (mode === "dialogue"
      ? project.speakers.some((s) => !s.voice_id)
      : !project.default_voice_id);

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">{t("app.title")}</h1>
        <div className="flex items-center gap-4">
          <Link href="/" className="text-sm underline underline-offset-4">
            {t("app.allProjects")}
          </Link>
          <LanguageToggle />
        </div>
      </header>

      {error && (
        <div
          role="alert"
          className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
        >
          {error}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-[1.3fr_1fr]">
        {/* Script */}
        <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            aria-label={t("editor.titleLabel")}
            placeholder={t("editor.untitled")}
            className="field w-full text-base font-medium"
          />

          <div className="flex gap-2">
            {(["monologue", "dialogue"] as const).map((m) => (
              <button
                key={m}
                onClick={() => {
                  setMode(m);
                  if (!project) {
                    setSourceText(m === "dialogue" ? SAMPLE_DIALOGUE : SAMPLE_MONOLOGUE);
                  }
                }}
                className={`chip ${mode === m ? "chip-active" : ""}`}
              >
                {m === "monologue" ? t("mode.monologue") : t("mode.dialogue")}
              </button>
            ))}
          </div>

          <textarea
            value={sourceText}
            onChange={(e) => setSourceText(e.target.value)}
            rows={12}
            aria-label={t("editor.scriptLabel")}
            placeholder={t("editor.placeholder")}
            className="field w-full resize-y font-mono text-sm leading-relaxed"
          />

          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={saveAndParse}
              disabled={busy !== null}
              className="btn-primary"
            >
              {busy === "Saving" ? t("editor.saving") : t("editor.saveParse")}
            </button>
            <button
              onClick={generate}
              disabled={busy !== null || !project || project.segments.length === 0 || Boolean(needsVoice)}
              className="btn-primary"
            >
              {busy === "Generating"
                ? t("editor.generating")
                : t("editor.generate")}
            </button>
          </div>

          {needsVoice && (
            <p className="text-xs text-amber-700 dark:text-amber-400">
              {t("editor.needsVoice")}
            </p>
          )}

          {job && busy === "Generating" && (
            <div className="space-y-1">
              <div className="h-1.5 rounded-full bg-slate-100 dark:bg-slate-800">
                <div
                  className="h-1.5 rounded-full bg-slate-900 transition-[width] dark:bg-slate-100"
                  style={{ width: `${job.progress}%` }}
                />
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {label("render", job.status)} — {job.progress}%
              </p>
            </div>
          )}
        </section>

        {/* Voice & audio settings */}
        <section className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
          <div>
            <label className="mb-1 block text-sm font-medium">
              {t("settings.generationSpeed", { speed: speed.toFixed(2) })}
            </label>
            <input
              type="range"
              min={0.7}
              max={1.4}
              step={0.05}
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
              className="w-full accent-slate-900 dark:accent-slate-100"
            />
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {t("settings.generationSpeedHint")}
            </p>
          </div>

          {mode === "dialogue" && project && project.speakers.length > 0 ? (
            <div className="space-y-4">
              {project.speakers.map((speaker) => (
                <div key={speaker.id}>
                  <h3 className="mb-2 text-sm font-semibold">
                    {t("settings.speaker", { label: speaker.label })}
                    {speaker.voice_id && (
                      <span className="ml-2 font-normal text-slate-500 dark:text-slate-400">
                        {voices.find((v) => v.id === speaker.voice_id)?.name}
                      </span>
                    )}
                  </h3>
                  <VoiceSelector
                    voices={voices}
                    selectedId={speaker.voice_id}
                    onSelect={(voiceId) => assignVoice(speaker.id, voiceId)}
                  />
                </div>
              ))}
            </div>
          ) : (
            <div>
              <h3 className="mb-2 text-sm font-semibold">{t("settings.voice")}</h3>
              <VoiceSelector
                voices={voices}
                selectedId={project?.default_voice_id ?? null}
                onSelect={setDefaultVoice}
              />
              {!project && (
                <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                  {t("settings.saveFirst")}
                </p>
              )}
            </div>
          )}
        </section>
      </div>

      {/* Segments */}
      {project && project.segments.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
          <h2 className="mb-2 text-sm font-semibold">
            {t("segments.heading", { count: project.segments.length })}
          </h2>
          <ol className="space-y-1 text-sm">
            {project.segments.map((segment) => {
              const speaker = project.speakers.find(
                (s) => s.id === segment.speaker_id,
              );
              return (
                <li
                  key={segment.id}
                  className="flex items-baseline gap-2 border-b border-slate-100 py-1.5 last:border-0 dark:border-slate-800"
                >
                  <span className="w-6 shrink-0 text-xs tabular-nums text-slate-400">
                    {segment.order_index + 1}
                  </span>
                  {speaker && (
                    <span className="shrink-0 text-xs font-semibold text-slate-500 dark:text-slate-400">
                      {speaker.label}
                    </span>
                  )}
                  <span className="flex-1">{segment.text}</span>
                  <span className="shrink-0 text-xs tabular-nums text-slate-400">
                    {segment.duration_ms
                      ? `${(segment.duration_ms / 1000).toFixed(1)}s`
                      : "—"}
                  </span>
                </li>
              );
            })}
          </ol>
        </section>
      )}

      <ListeningPlayer
        key={job?.audio_url ?? "none"}
        src={job?.status === "completed" ? job.audio_url : null}
        segments={project?.segments ?? []}
        speakers={project?.speakers ?? []}
        transcriptVisible={transcriptVisible}
        onToggleTranscript={() => setTranscriptVisible((v) => !v)}
      />
    </div>
  );
}
