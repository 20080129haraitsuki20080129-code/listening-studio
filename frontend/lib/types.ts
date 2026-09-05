export type Mode = "monologue" | "dialogue" | "listening_test" | "shadowing";

export type Voice = {
  id: string;
  provider: string;
  provider_voice_id: string;
  name: string;
  language: string;
  locale: string | null;
  accent: string | null;
  gender: string;
  age_group: string;
  style_tags: string[];
  preview_url: string | null;
  enabled: boolean;
};

export type Speaker = {
  id: string;
  project_id: string;
  label: string;
  /** Which style combination this slot corresponds to, for styled dialogues. */
  style_key: string | null;
  display_name: string;
  voice_id: string | null;
  generation_speed: number;
  default_pause_before_ms: number;
  default_pause_after_ms: number;
};

export type Segment = {
  id: string;
  project_id: string;
  order_index: number;
  speaker_id: string | null;
  text: string;
  voice_id_override: string | null;
  generation_speed_override: number | null;
  pause_before_ms: number;
  pause_after_ms: number;
  audio_asset_id: string | null;
  duration_ms: number | null;
};

export type Project = {
  id: string;
  title: string;
  mode: Mode;
  source_text: string;
  /** True when speakers come from text styling rather than [A] markers. */
  styled_dialogue: boolean;
  transcript_visible_default: boolean;
  default_voice_id: string | null;
  default_generation_speed: number;
  sentence_pause_ms: number;
  paragraph_pause_ms: number;
  created_at: string;
  updated_at: string;
  speakers: Speaker[];
  segments: Segment[];
};

export type ProjectSummary = Pick<
  Project,
  "id" | "title" | "mode" | "created_at" | "updated_at"
>;

export type RenderJob = {
  id: string;
  project_id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  audio_asset_id: string | null;
  audio_url: string | null;
  duration_ms: number | null;
  error: { code: string; message: string } | null;
};
