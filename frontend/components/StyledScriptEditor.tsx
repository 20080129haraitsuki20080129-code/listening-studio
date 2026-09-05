"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useTranslation } from "@/lib/i18n";

type Mark = "bold" | "italic" | "underline";

const SHORTCUTS: Record<string, Mark> = { b: "bold", i: "italic", u: "underline" };

type Props = {
  html: string;
  onChange: (html: string) => void;
  ariaLabel: string;
  placeholder: string;
};

/**
 * A script editor where a speaker is marked by styling the line, the way a
 * word processor does, instead of typing [A] / [B].
 *
 * `document.execCommand` is deprecated but remains the only API every browser
 * implements for this, and the alternative is a rich-text dependency far larger
 * than the three marks needed here. The parser accepts whatever markup any
 * browser produces for bold/italic/underline, so the inconsistency is absorbed
 * on the way in rather than fought here.
 */
export function StyledScriptEditor({
  html,
  onChange,
  ariaLabel,
  placeholder,
}: Props) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDivElement | null>(null);
  const [active, setActive] = useState<Record<Mark, boolean>>({
    bold: false,
    italic: false,
    underline: false,
  });

  // Only write into the DOM when the incoming value genuinely differs;
  // assigning innerHTML on every render would destroy the caret.
  useEffect(() => {
    const node = ref.current;
    if (node && node.innerHTML !== html) node.innerHTML = html;
  }, [html]);

  const refreshActiveMarks = useCallback(() => {
    try {
      setActive({
        bold: document.queryCommandState("bold"),
        italic: document.queryCommandState("italic"),
        underline: document.queryCommandState("underline"),
      });
    } catch {
      // queryCommandState throws in some embedded contexts; the toolbar just
      // stops highlighting, which is cosmetic.
    }
  }, []);

  const apply = useCallback(
    (mark: Mark) => {
      ref.current?.focus();
      document.execCommand(mark, false);
      onChange(ref.current?.innerHTML ?? "");
      refreshActiveMarks();
    },
    [onChange, refreshActiveMarks],
  );

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      // Same chords as Word: Cmd on macOS, Ctrl elsewhere.
      if (!event.metaKey && !event.ctrlKey) return;
      const mark = SHORTCUTS[event.key.toLowerCase()];
      if (!mark) return;
      event.preventDefault();
      apply(mark);
    },
    [apply],
  );

  const onPaste = useCallback(
    (event: React.ClipboardEvent<HTMLDivElement>) => {
      // Paste as plain text: styling carried in from elsewhere would silently
      // reassign speakers.
      event.preventDefault();
      const text = event.clipboardData.getData("text/plain");
      document.execCommand("insertText", false, text);
      onChange(ref.current?.innerHTML ?? "");
    },
    [onChange],
  );

  const isEmpty = !html || html === "<br>" || html.trim() === "";

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1">
        {(["bold", "italic", "underline"] as const).map((mark) => (
          <button
            key={mark}
            type="button"
            onClick={() => apply(mark)}
            aria-pressed={active[mark]}
            aria-label={t(`editor.${mark}` as never)}
            title={`${t(`editor.${mark}` as never)} (⌘/Ctrl+${mark[0].toUpperCase()})`}
            className={`h-8 w-8 rounded border text-sm transition ${
              active[mark]
                ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                : "border-slate-300 hover:border-slate-500 dark:border-slate-700"
            } ${mark === "bold" ? "font-bold" : ""} ${
              mark === "italic" ? "italic" : ""
            } ${mark === "underline" ? "underline" : ""}`}
          >
            {mark === "bold" ? "B" : mark === "italic" ? "I" : "U"}
          </button>
        ))}
        <span className="ml-2 text-xs text-slate-500 dark:text-slate-400">
          {t("editor.styleHint")}
        </span>
      </div>

      <div className="relative">
        {isEmpty && (
          <div className="pointer-events-none absolute left-3 top-2 whitespace-pre-wrap font-mono text-sm text-slate-400">
            {placeholder}
          </div>
        )}
        <div
          ref={ref}
          role="textbox"
          aria-multiline="true"
          aria-label={ariaLabel}
          contentEditable
          suppressContentEditableWarning
          onInput={(e) => onChange(e.currentTarget.innerHTML)}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          onKeyUp={refreshActiveMarks}
          onMouseUp={refreshActiveMarks}
          className="field min-h-64 w-full overflow-y-auto whitespace-pre-wrap font-mono text-sm leading-relaxed"
        />
      </div>
    </div>
  );
}
