"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { LanguageToggle } from "@/components/LanguageToggle";
import { SignOutButton } from "@/components/SignOutButton";
import { ListeningPlayer } from "@/components/ListeningPlayer";
import { StyledScriptEditor } from "@/components/StyledScriptEditor";
import { VoiceSelector } from "@/components/VoiceSelector";
import { ApiError, api, downloadUrls } from "@/lib/api";
import { type MessageKey, useDynamicLabel, useTranslation } from "@/lib/i18n";
import { type StyleKey, styleClasses } from "@/lib/styles";
import type { Mode, Project, RenderJob, SpeedLevel, Voice } from "@/lib/types";

// Styled sample: each line's formatting picks its speaker, so nothing has to
// be typed to mark a turn.
const SAMPLE_DIALOGUE_HTML = [
  "<div>Have you finished the report? Dr. Chen asked for it by 3.30 p.m.</div>",
  "<div><b>Not yet. I found something interesting in the U.S. data.</b></div>",
  "<div>What did you find?</div>",
].join("");

const SAMPLE_MONOLOGUE = `Climate change is altering migration patterns across the world. Researchers say the shift is accelerating, and that some species are moving toward the poles faster than models predicted.`;

export function Studio({ projectId }: { projectId?: string }) {
  const { t } = useTranslation();
  const label = useDynamicLabel();
  const [project, setProject] = useState<Project | null>(null);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [title, setTitle] = useState("");
  const [mode, setMode] = useState<Mode>("monologue");
  const [sourceText, setSourceText] = useState(SAMPLE_MONOLOGUE);
  const [styled, setStyled] = useState(false);
  const [speedLevels, setSpeedLevels] = useState<SpeedLevel[]>([]);
  const [speedLevel, setSpeedLevel] = useState(4);
  const [repeatCount, setRepeatCount] = useState(1);
  const [repeatGapMs, setRepeatGapMs] = useState(3000);
  const [speakerCount, setSpeakerCount] = useState(2);
  const [transcriptVisible, setTranscriptVisible] = useState(true);

  const [job, setJob] = useState<RenderJob | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Assigning voices to two speakers in quick succession fires two reloads.
  // Without a guard a slower earlier response can land last and revert the
  // newer selection, so stale loads are discarded.
  const loadSeq = useRef(0);

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
      const levels = await api.speedLevels();
      setSpeedLevels(levels.items);
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
      const seq = ++loadSeq.current;
      try {
        const p = await api.getProject(id);
        if (seq !== loadSeq.current) return;
        setProject(p);
        setTitle(p.title);
        setMode(p.mode);
        setSourceText(p.source_text);
        setStyled(p.styled_dialogue);
        setRepeatCount(p.repeat_count);
        setRepeatGapMs(p.pause_between_repeats_ms);
        if (p.speakers.length > 0) setSpeakerCount(p.speakers.length);
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

  // A project stores a speed multiplier, so map it back onto the nearest
  // preset once the presets have arrived. Without this a saved project always
  // reopens showing the default level, whatever pace it was saved at.
  useEffect(() => {
    if (!project || speedLevels.length === 0) return;
    const stored = Number(project.default_generation_speed);
    const nearest = speedLevels.reduce((best, entry) =>
      Math.abs(entry.speed - stored) < Math.abs(best.speed - stored) ? entry : best,
    );
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSpeedLevel(nearest.level);
  }, [project, speedLevels]);

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
      const chosen = speedLevels.find((entry) => entry.level === speedLevel);
      await api.updateProject(current.id, {
        title: effectiveTitle,
        mode,
        default_generation_speed: chosen?.speed ?? 1.0,
        repeat_count: repeatCount,
        pause_between_repeats_ms: repeatGapMs,
        transcript_visible_default: transcriptVisible,
      });
      // Parsing owns the roster: the script says how many speakers there are,
      // whether they are marked with styling or with [A] / [B]. The count
      // control adjusts it afterwards; applying it here would fight the parse
      // and silently discard speakers the script had just established.
      await api.parseProject(current.id, { source_text: sourceText, mode });
      await loadProject(current.id);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(null);
    }
  }, [
    project,
    title,
    mode,
    sourceText,
    speedLevel,
    speedLevels,
    repeatCount,
    repeatGapMs,
    transcriptVisible,
    loadProject,
    fail,
    t,
  ]);

  const applySpeakerCount = useCallback(
    async (count: number) => {
      setSpeakerCount(count);
      if (!project) return;
      try {
        await api.setSpeakerCount(project.id, count);
        await loadProject(project.id);
      } catch (e) {
        fail(e);
      }
    },
    [project, loadProject, fail],
  );

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

  const currentLevel = speedLevels.find((entry) => entry.level === speedLevel);

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
          <SignOutButton />
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
                    setSourceText(
                      m === "dialogue" ? SAMPLE_DIALOGUE_HTML : SAMPLE_MONOLOGUE,
                    );
                    setStyled(m === "dialogue");
                  }
                }}
                className={`chip ${mode === m ? "chip-active" : ""}`}
              >
                {m === "monologue" ? t("mode.monologue") : t("mode.dialogue")}
              </button>
            ))}
          </div>

          {mode === "dialogue" ? (
            <StyledScriptEditor
              html={sourceText}
              onChange={setSourceText}
              ariaLabel={t("editor.scriptLabel")}
              placeholder={t("editor.placeholder")}
            />
          ) : (
            <textarea
              value={sourceText}
              onChange={(e) => setSourceText(e.target.value)}
              rows={12}
              aria-label={t("editor.scriptLabel")}
              placeholder={t("editor.placeholder")}
              className="field w-full resize-y font-mono text-sm leading-relaxed"
            />
          )}

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
          {/* Seven presets, labelled by pace rather than by a bare multiplier:
              "about 140-150 words/min" is a thing you can aim at. */}
          <div>
            <label
              htmlFor="speed-level"
              className="mb-1 block text-sm font-medium"
            >
              {t("settings.speedLevel")}
            </label>
            <input
              id="speed-level"
              type="range"
              min={1}
              max={speedLevels.length || 7}
              step={1}
              value={speedLevel}
              onChange={(e) => setSpeedLevel(Number(e.target.value))}
              aria-valuetext={
                currentLevel
                  ? t("settings.speedLevelValue", {
                      level: currentLevel.level,
                      wpm: currentLevel.wpm_typical,
                    })
                  : String(speedLevel)
              }
              className="w-full accent-slate-900 dark:accent-slate-100"
            />
            <div className="flex justify-between text-[10px] text-slate-400">
              {(speedLevels.length ? speedLevels : []).map((entry) => (
                <span key={entry.level}>{entry.level}</span>
              ))}
            </div>
            {currentLevel && (
              <>
                <p className="text-sm font-medium tabular-nums">
                  {t("settings.speedLevelValue", {
                    level: currentLevel.level,
                    wpm: currentLevel.wpm_typical,
                  })}
                  {currentLevel.reference && (
                    <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-normal dark:bg-slate-800">
                      {t(
                        `settings.speedRef.${currentLevel.reference}` as MessageKey,
                      )}
                    </span>
                  )}
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {t("settings.speedSpread", {
                    min: currentLevel.wpm_min,
                    max: currentLevel.wpm_max,
                  })}
                </p>
              </>
            )}
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {t("settings.speedLevelHint")}
            </p>
            {/* The level advertises an estimate; this is what the render
                actually produced. */}
            {project?.actual_wpm != null && (
              <p className="mt-1 text-sm font-medium tabular-nums text-slate-700 dark:text-slate-300">
                {t("settings.actualWpm", { wpm: Math.round(project.actual_wpm) })}
                <span className="ml-2 text-xs font-normal text-slate-500 dark:text-slate-400">
                  {t("settings.actualWpmHint")}
                </span>
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label
                htmlFor="repeat-count"
                className="mb-1 block text-sm font-medium"
              >
                {t("settings.repeatCount")}
              </label>
              <select
                id="repeat-count"
                value={repeatCount}
                onChange={(e) => setRepeatCount(Number(e.target.value))}
                className="field w-full"
              >
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n === 1
                      ? t("settings.repeatOnce")
                      : t("settings.repeatTimes", { n })}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="repeat-gap"
                className="mb-1 block text-sm font-medium"
              >
                {t("settings.repeatGap")}
              </label>
              <select
                id="repeat-gap"
                value={repeatGapMs}
                onChange={(e) => setRepeatGapMs(Number(e.target.value))}
                disabled={repeatCount === 1}
                className="field w-full disabled:opacity-40"
              >
                {[1000, 2000, 3000, 5000, 8000, 10000].map((ms) => (
                  <option key={ms} value={ms}>
                    {t("settings.seconds", { n: ms / 1000 })}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {mode === "dialogue" ? (
            <div className="space-y-4">
              {/* With styles the roster follows the script: how many
                  formatting combinations appear is how many speakers there
                  are, so a count control would only contradict it. */}
              {!styled && (
                <div>
                  <label
                    htmlFor="speaker-count"
                    className="mb-1 block text-sm font-medium"
                  >
                    {t("speakers.count")}
                  </label>
                  <select
                    id="speaker-count"
                    value={speakerCount}
                    onChange={(e) => applySpeakerCount(Number(e.target.value))}
                    className="field"
                  >
                    {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {project?.speakers.map((speaker, index) => (
                <div key={speaker.id}>
                  <h3 className="mb-2 text-sm font-semibold">
                    {t("speakers.voiceN", { n: index + 1 })}
                    {styled && speaker.style_key ? (
                      <span
                        className={`ml-2 text-xs font-normal text-slate-500 dark:text-slate-400 ${styleClasses(
                          speaker.style_key as StyleKey,
                        )}`}
                      >
                        {t(`style.${speaker.style_key}` as MessageKey)}
                      </span>
                    ) : (
                      <span className="ml-2 text-xs font-normal text-slate-500 dark:text-slate-400">
                        {t("speakers.marker", { label: `[${speaker.label}]` })}
                      </span>
                    )}
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
                    disabled={busy !== null}
                  />
                </div>
              ))}
              {!project && (
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {t("settings.saveFirst")}
                </p>
              )}
            </div>
          ) : (
            <div>
              <h3 className="mb-2 text-sm font-semibold">{t("settings.voice")}</h3>
              <VoiceSelector
                voices={voices}
                selectedId={project?.default_voice_id ?? null}
                onSelect={setDefaultVoice}
                disabled={!project || busy !== null}
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
          <h2 className="mb-2 flex items-baseline gap-2 text-sm font-semibold">
            {t("segments.heading", { count: project.segments.length })}
            <span className="font-normal text-slate-500 dark:text-slate-400">
              {t("settings.words", { n: project.word_count })}
            </span>
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
                    {t("settings.words", { n: segment.word_count })}
                  </span>
                  <span className="w-12 shrink-0 text-right text-xs tabular-nums text-slate-400">
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

      {project && project.segments.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
          <h2 className="mb-2 text-sm font-semibold">{t("download.heading")}</h2>
          <div className="flex flex-wrap items-center gap-2">
            {/* The transcript needs only a parsed script; the audio needs a
                finished render. */}
            <a
              href={downloadUrls.transcript(project.id)}
              download
              className="chip"
            >
              {t("download.transcript")}
            </a>
            {job?.status === "completed" ? (
              <a
                href={downloadUrls.audio(job.id)}
                download
                className="chip"
              >
                {t("download.audio")}
              </a>
            ) : (
              <span className="text-xs text-slate-500 dark:text-slate-400">
                {t("download.needsRender")}
              </span>
            )}
          </div>
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
