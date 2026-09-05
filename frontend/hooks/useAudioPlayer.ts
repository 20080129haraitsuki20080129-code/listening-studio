"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type AudioPlayerState = {
  playing: boolean;
  currentTime: number;
  duration: number;
  playbackRate: number;
  volume: number;
  loopStart: number | null;
  loopEnd: number | null;
  loopEnabled: boolean;
};

/**
 * Player state for the listening UI.
 *
 * State is not reset when `src` changes -- the consumer remounts the player
 * with a `key` instead, so stale A/B markers can never point into a different
 * recording.
 *
 * playbackRate only affects playback; it never touches the stored audio
 * (SPEC section 10.2). Generation speed is a separate, server-side concept.
 */
export function useAudioPlayer(src: string | null) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [state, setState] = useState<AudioPlayerState>({
    playing: false,
    currentTime: 0,
    duration: 0,
    playbackRate: 1,
    volume: 1,
    loopStart: null,
    loopEnd: null,
    loopEnabled: false,
  });

  // Keep the loop bounds in a ref: timeupdate fires often, and reading them
  // from state would mean re-subscribing the listener on every change.
  const loopRef = useRef({
    start: null as number | null,
    end: null as number | null,
    enabled: false,
  });
  useEffect(() => {
    loopRef.current = {
      start: state.loopStart,
      end: state.loopEnd,
      enabled: state.loopEnabled,
    };
  }, [state.loopStart, state.loopEnd, state.loopEnabled]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onLoaded = () =>
      setState((s) => ({ ...s, duration: audio.duration || 0 }));
    const onTime = () => {
      const { start, end, enabled } = loopRef.current;
      if (enabled && start !== null && end !== null && audio.currentTime >= end) {
        audio.currentTime = start;
        void audio.play();
      }
      setState((s) => ({ ...s, currentTime: audio.currentTime }));
    };
    const onPlay = () => setState((s) => ({ ...s, playing: true }));
    const onPause = () => setState((s) => ({ ...s, playing: false }));
    const onEnded = () => setState((s) => ({ ...s, playing: false }));

    audio.addEventListener("loadedmetadata", onLoaded);
    audio.addEventListener("timeupdate", onTime);
    audio.addEventListener("play", onPlay);
    audio.addEventListener("pause", onPause);
    audio.addEventListener("ended", onEnded);
    return () => {
      audio.removeEventListener("loadedmetadata", onLoaded);
      audio.removeEventListener("timeupdate", onTime);
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("pause", onPause);
      audio.removeEventListener("ended", onEnded);
    };
  }, [src]);

  const toggle = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) void audio.play();
    else audio.pause();
  }, []);

  const seek = useCallback((time: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = time;
    setState((s) => ({ ...s, currentTime: time }));
  }, []);

  const setPlaybackRate = useCallback((rate: number) => {
    const audio = audioRef.current;
    if (audio) audio.playbackRate = rate;
    setState((s) => ({ ...s, playbackRate: rate }));
  }, []);

  const setVolume = useCallback((volume: number) => {
    const audio = audioRef.current;
    if (audio) audio.volume = volume;
    setState((s) => ({ ...s, volume }));
  }, []);

  const markA = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    setState((s) => {
      const start = audio.currentTime;
      // Keep A before B; marking A past B would create an empty loop.
      const end = s.loopEnd !== null && s.loopEnd <= start ? null : s.loopEnd;
      return { ...s, loopStart: start, loopEnd: end };
    });
  }, []);

  const markB = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    setState((s) => {
      const end = audio.currentTime;
      if (s.loopStart !== null && end <= s.loopStart) return s;
      return { ...s, loopEnd: end };
    });
  }, []);

  const clearLoop = useCallback(
    () =>
      setState((s) => ({
        ...s,
        loopStart: null,
        loopEnd: null,
        loopEnabled: false,
      })),
    [],
  );

  const toggleLoop = useCallback(
    () =>
      setState((s) =>
        s.loopStart === null || s.loopEnd === null
          ? s
          : { ...s, loopEnabled: !s.loopEnabled },
      ),
    [],
  );

  return {
    audioRef,
    state,
    toggle,
    seek,
    setPlaybackRate,
    setVolume,
    markA,
    markB,
    clearLoop,
    toggleLoop,
    canLoop: state.loopStart !== null && state.loopEnd !== null,
  };
}

export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
