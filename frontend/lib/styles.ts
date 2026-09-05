/**
 * Speaker styles.
 *
 * Bold, italic and underline are independent, so there are exactly eight
 * combinations -- which is why a styled dialogue tops out at eight speakers.
 * This order matches the backend's SLOT_ORDER: Voice 1 is always plain, Voice
 * 2 always bold, and so on, so the mapping never shifts as a script is edited.
 */
export const STYLE_SLOTS = [
  "plain",
  "bold",
  "italic",
  "underline",
  "bold_italic",
  "bold_underline",
  "italic_underline",
  "bold_italic_underline",
] as const;

export type StyleKey = (typeof STYLE_SLOTS)[number];

const BOLD = 1;
const ITALIC = 2;
const UNDERLINE = 4;

const MASKS: Record<StyleKey, number> = {
  plain: 0,
  bold: BOLD,
  italic: ITALIC,
  underline: UNDERLINE,
  bold_italic: BOLD | ITALIC,
  bold_underline: BOLD | UNDERLINE,
  italic_underline: ITALIC | UNDERLINE,
  bold_italic_underline: BOLD | ITALIC | UNDERLINE,
};

export function maskOf(key: StyleKey): number {
  return MASKS[key];
}

/** Tailwind classes that render a sample of the style. */
export function styleClasses(key: StyleKey): string {
  const mask = MASKS[key];
  return [
    mask & BOLD ? "font-bold" : "",
    mask & ITALIC ? "italic" : "",
    mask & UNDERLINE ? "underline" : "",
  ]
    .filter(Boolean)
    .join(" ");
}
