"use client";

import { audioUrl } from "@/lib/api";
import { formatTime, useAudioPlayer } from "@/hooks/useAudioPlayer";
import { useTranslation } from "@/lib/i18n";
import type { Segment, Speaker } from "@/lib/types";

const PLAYBACK_RATES = [0.5, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0];

type Props = {
  src: string | null;
  segments: Segment[];
  speakers: Speaker[];
  transcriptVisible: boolean;
  onToggleTranscript: () => void;
};

export function ListeningPlayer({
  src,
  segments,
  speakers,
  transcriptVisible,
  onToggleTranscript,
}: Props) {
  const { t } = useTranslation();
  const {
    audioRef,
    state,
    toggle,
    seek,
    setPlaybackRate,
    markA,
    markB,
    clearLoop,
    toggleLoop,
    canLoop,
  } = useAudioPlayer(src);
  const speakerLabel = (id: string | null) =>
    speakers.find((s) => s.id === id)?.label ?? null;

  if (!src) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
        {t("player.empty")}
      </div>
    );
  }

  const progress = state.duration
    ? (state.currentTime / state.duration) * 100
    : 0;

  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
      <audio ref={audioRef} src={audioUrl(src)} preload="metadata" />

      <div className="flex items-center gap-3">
        <button
          onClick={toggle}
          aria-label={state.playing ? t("player.pause") : t("player.play")}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-slate-900 text-white transition hover:bg-slate-700 dark:bg-slate-100 dark:text-slate-900"
        >
          {state.playing ? "❚❚" : "▶"}
        </button>

        <div className="flex-1">
          <input
            type="range"
            min={0}
            max={state.duration || 0}
            step={0.01}
            value={state.currentTime}
            onChange={(e) => seek(Number(e.target.value))}
            aria-label={t("player.seek")}
            className="w-full accent-slate-900 dark:accent-slate-100"
          />
          <div className="flex justify-between text-xs tabular-nums text-slate-500 dark:text-slate-400">
            <span>{formatTime(state.currentTime)}</span>
            <span>{formatTime(state.duration)}</span>
          </div>
        </div>
      </div>

      {/* A-B repeat */}
      <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3 dark:border-slate-800">
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
          {t("player.abRepeat")}
        </span>
        <button onClick={markA} className="chip">
          {t("player.setA")}
          {state.loopStart !== null && ` (${formatTime(state.loopStart)})`}
        </button>
        <button onClick={markB} className="chip">
          {t("player.setB")}
          {state.loopEnd !== null && ` (${formatTime(state.loopEnd)})`}
        </button>
        <button
          onClick={toggleLoop}
          disabled={!canLoop}
          className={`chip ${state.loopEnabled ? "chip-active" : ""} disabled:opacity-40`}
        >
          {state.loopEnabled ? t("player.looping") : t("player.loop")}
        </button>
        <button onClick={clearLoop} className="chip">
          {t("player.clear")}
        </button>
      </div>

      {/* Playback rate. Distinct from generation speed: this never changes
          the stored audio. */}
      <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3 dark:border-slate-800">
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
          {t("player.playbackRate")}
        </span>
        {PLAYBACK_RATES.map((rate) => (
          <button
            key={rate}
            onClick={() => setPlaybackRate(rate)}
            className={`chip ${state.playbackRate === rate ? "chip-active" : ""}`}
          >
            {rate}×
          </button>
        ))}
      </div>

      <div className="border-t border-slate-100 pt-3 dark:border-slate-800">
        <button onClick={onToggleTranscript} className="chip">
          {transcriptVisible
            ? t("player.hideTranscript")
            : t("player.showTranscript")}
        </button>

        {transcriptVisible ? (
          <ol className="mt-3 space-y-1.5 text-sm">
            {segments.map((segment) => {
              const label = speakerLabel(segment.speaker_id);
              return (
                <li key={segment.id} className="flex gap-2">
                  {label && (
                    <span className="shrink-0 font-semibold text-slate-500 dark:text-slate-400">
                      {label}
                    </span>
                  )}
                  <span className="text-slate-800 dark:text-slate-200">
                    {segment.text}
                  </span>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="mt-3 rounded border border-dashed border-slate-300 p-4 text-center text-sm text-slate-400 dark:border-slate-700">
            {t("player.transcriptHidden")}
          </p>
        )}
      </div>

      <div
        className="h-1 rounded-full bg-slate-100 dark:bg-slate-800"
        aria-hidden
      >
        <div
          className="h-1 rounded-full bg-slate-900 transition-[width] dark:bg-slate-100"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}
