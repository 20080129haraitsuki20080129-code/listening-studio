/**
 * UI copy for each supported locale.
 *
 * Two locales and a few dozen strings do not justify an i18n dependency, and
 * SPEC section 19 asks not to add libraries without a clear need. `ja` is typed
 * against `en`, so a key added to one and forgotten in the other fails to
 * compile.
 */

export const LOCALES = ["en", "ja"] as const;
export type Locale = (typeof LOCALES)[number];

export const LOCALE_NAMES: Record<Locale, string> = {
  en: "English",
  ja: "日本語",
};

const en = {
  // Shell
  "app.title": "Listening Studio",
  "app.allProjects": "All projects",
  "app.language": "Language",

  // Project list
  "projects.new": "New project",
  "projects.loading": "Loading…",
  "projects.empty": "No projects yet.",
  "projects.delete": "Delete",
  "projects.updated": "{mode} · updated {date}",
  "projects.loadFailed": "Could not load projects.",

  // Script editor
  "editor.titleLabel": "Project title",
  "editor.untitled": "Untitled",
  "editor.scriptLabel": "English script",
  "editor.placeholder":
    "Paste English text.\n\nFor dialogue use [A] / [B] on their own lines.",
  "editor.saveParse": "Save & parse",
  "editor.saving": "Saving…",
  "editor.generate": "Generate audio",
  "editor.generating": "Generating…",
  "editor.needsVoice": "Assign a voice before generating.",

  // Modes
  "mode.monologue": "Monologue",
  "mode.dialogue": "Dialogue",

  // Settings panel
  "settings.generationSpeed": "Generation speed: {speed}×",
  "settings.generationSpeedHint":
    "Applied when the audio is generated. Playback rate is separate.",
  "settings.voice": "Voice",
  "settings.speaker": "Speaker {label}",
  "settings.saveFirst": "Save the project first to pick a voice.",

  // Voice selector
  "voice.allAccents": "All accents",
  "voice.allGenders": "All genders",
  "voice.allProviders": "All providers",
  "voice.accent": "Accent",
  "voice.gender": "Gender",
  "voice.provider": "Provider",
  "voice.searchPlaceholder": "Search name",
  "voice.searchLabel": "Search voices",
  "voice.count": "{shown} of {total} voices",
  "voice.noMatches": "No voices match these filters.",

  "editor.bold": "Bold",
  "editor.italic": "Italic",
  "editor.underline": "Underline",
  "editor.styleHint": "Style a line to assign it to a voice",
  "editor.markerMode": "Markers ([A] / [B])",
  "editor.styleMode": "Styles (bold / italic / underline)",

  // Speakers
  "speakers.count": "Number of speakers",
  "speakers.voiceN": "Voice {n}",
  "speakers.marker": "marked {label} in the script",

  "style.plain": "Plain",
  "style.bold": "Bold",
  "style.italic": "Italic",
  "style.underline": "Underline",
  "style.bold_italic": "Bold + italic",
  "style.bold_underline": "Bold + underline",
  "style.italic_underline": "Italic + underline",
  "style.bold_italic_underline": "Bold + italic + underline",
  "style.unused": "not used in the script yet",

  // Downloads
  "download.heading": "Download",
  "download.audio": "Audio (MP3)",
  "download.transcript": "Script (PDF)",
  "download.needsRender": "Generate the audio first.",

  // Segments
  "segments.heading": "Segments ({count})",

  // Player
  "player.empty": "Generate audio to start listening.",
  "player.play": "Play",
  "player.pause": "Pause",
  "player.seek": "Seek",
  "player.abRepeat": "A-B repeat",
  "player.setA": "Set A",
  "player.setB": "Set B",
  "player.loop": "Loop",
  "player.looping": "Looping",
  "player.clear": "Clear",
  "player.playbackRate": "Playback rate",
  "player.hideTranscript": "Hide transcript",
  "player.showTranscript": "Show transcript",
  "player.transcriptHidden": "Transcript hidden — listen first.",

  // Render status
  "render.queued": "queued",
  "render.running": "running",
  "render.completed": "completed",
  "render.failed": "failed",
  "render.cancelled": "cancelled",

  // Accents
  "accent.american": "American",
  "accent.british": "British",
  "accent.australian": "Australian",
  "accent.canadian": "Canadian",
  "accent.irish": "Irish",
  "accent.indian": "Indian",
  "accent.scottish": "Scottish",
  "accent.new_zealand": "New Zealand",
  "accent.south_african": "South African",
  "accent.singaporean": "Singaporean",
  "accent.unknown": "Unknown",

  // Genders
  "gender.female": "Female",
  "gender.male": "Male",
  "gender.neutral": "Neutral",
  "gender.unknown": "Unknown",

  // Errors. Keyed by the API's normalized error codes so the message can be
  // localized without the backend having to know about locales.
  "error.generic": "Something went wrong.",
  "error.NETWORK_ERROR":
    "Could not reach the server. Is the backend running?",
  "error.INVALID_SCRIPT": "The script could not be processed.",
  "error.NOT_FOUND": "That item no longer exists.",
  "error.VOICE_NOT_FOUND": "The selected voice does not exist.",
  "error.VOICE_DISABLED": "The selected voice is disabled.",
  "error.PROVIDER_UNAVAILABLE":
    "The speech provider is temporarily unavailable.",
  "error.PROVIDER_RATE_LIMITED":
    "Speech generation is temporarily rate limited.",
  "error.PROVIDER_AUTH_FAILED":
    "The speech provider rejected the credentials.",
  "error.PROVIDER_REQUEST_FAILED":
    "The speech provider could not process the request.",
  "error.AUDIO_PROCESSING_FAILED": "Audio processing failed.",
  "error.STORAGE_FAILED": "Storing the generated audio failed.",
  "error.RENDER_CANCELLED": "The render was cancelled.",
} as const;

export type MessageKey = keyof typeof en;

const ja: Record<MessageKey, string> = {
  "app.title": "Listening Studio",
  "app.allProjects": "プロジェクト一覧",
  "app.language": "言語",

  "projects.new": "新規プロジェクト",
  "projects.loading": "読み込み中…",
  "projects.empty": "プロジェクトはまだありません。",
  "projects.delete": "削除",
  "projects.updated": "{mode} · 更新 {date}",
  "projects.loadFailed": "プロジェクトを読み込めませんでした。",

  "editor.titleLabel": "プロジェクト名",
  "editor.untitled": "無題",
  "editor.scriptLabel": "英文スクリプト",
  "editor.placeholder":
    "英文を貼り付けてください。\n\n会話にする場合は [A] / [B] を行頭に置きます。",
  "editor.saveParse": "保存して解析",
  "editor.saving": "保存中…",
  "editor.generate": "音声を生成",
  "editor.generating": "生成中…",
  "editor.needsVoice": "生成する前に声を割り当ててください。",

  "mode.monologue": "単読",
  "mode.dialogue": "会話",

  "settings.generationSpeed": "生成時の話速: {speed}×",
  "settings.generationSpeedHint":
    "音声生成時に適用されます。再生速度とは別の設定です。",
  "settings.voice": "声",
  "settings.speaker": "話者 {label}",
  "settings.saveFirst": "声を選ぶには、先にプロジェクトを保存してください。",

  "voice.allAccents": "すべてのアクセント",
  "voice.allGenders": "すべての性別",
  "voice.allProviders": "すべてのプロバイダ",
  "voice.accent": "アクセント",
  "voice.gender": "性別",
  "voice.provider": "プロバイダ",
  "voice.searchPlaceholder": "名前で検索",
  "voice.searchLabel": "声を検索",
  "voice.count": "{total}件中 {shown}件",
  "voice.noMatches": "条件に一致する声がありません。",

  "editor.bold": "太字",
  "editor.italic": "斜体",
  "editor.underline": "下線",
  "editor.styleHint": "行に書式を付けると、その声に割り当てられます",
  "editor.markerMode": "記号で指定（[A] / [B]）",
  "editor.styleMode": "書式で指定（太字・斜体・下線）",

  "style.plain": "書式なし",
  "style.bold": "太字",
  "style.italic": "斜体",
  "style.underline": "下線",
  "style.bold_italic": "太字＋斜体",
  "style.bold_underline": "太字＋下線",
  "style.italic_underline": "斜体＋下線",
  "style.bold_italic_underline": "太字＋斜体＋下線",
  "style.unused": "スクリプト内で未使用",

  "speakers.count": "話者の人数",
  "speakers.voiceN": "声{n}",
  "speakers.marker": "スクリプト内の {label}",

  "download.heading": "ダウンロード",
  "download.audio": "音声 (MP3)",
  "download.transcript": "スクリプト (PDF)",
  "download.needsRender": "先に音声を生成してください。",

  "segments.heading": "セグメント ({count})",

  "player.empty": "音声を生成すると再生できます。",
  "player.play": "再生",
  "player.pause": "一時停止",
  "player.seek": "シーク",
  "player.abRepeat": "A-Bリピート",
  "player.setA": "A地点",
  "player.setB": "B地点",
  "player.loop": "リピート",
  "player.looping": "リピート中",
  "player.clear": "解除",
  "player.playbackRate": "再生速度",
  "player.hideTranscript": "スクリプトを隠す",
  "player.showTranscript": "スクリプトを表示",
  "player.transcriptHidden": "スクリプトは非表示です — まず聴いてみましょう。",

  "render.queued": "待機中",
  "render.running": "生成中",
  "render.completed": "完了",
  "render.failed": "失敗",
  "render.cancelled": "キャンセル",

  "accent.american": "アメリカ英語",
  "accent.british": "イギリス英語",
  "accent.australian": "オーストラリア英語",
  "accent.canadian": "カナダ英語",
  "accent.irish": "アイルランド英語",
  "accent.indian": "インド英語",
  "accent.scottish": "スコットランド英語",
  "accent.new_zealand": "ニュージーランド英語",
  "accent.south_african": "南アフリカ英語",
  "accent.singaporean": "シンガポール英語",
  "accent.unknown": "不明",

  "gender.female": "女性",
  "gender.male": "男性",
  "gender.neutral": "中性",
  "gender.unknown": "不明",

  "error.generic": "問題が発生しました。",
  "error.NETWORK_ERROR":
    "サーバーに接続できません。バックエンドは起動していますか？",
  "error.INVALID_SCRIPT": "スクリプトを処理できませんでした。",
  "error.NOT_FOUND": "対象が見つかりません。",
  "error.VOICE_NOT_FOUND": "選択された声が存在しません。",
  "error.VOICE_DISABLED": "選択された声は無効になっています。",
  "error.PROVIDER_UNAVAILABLE": "音声プロバイダが一時的に利用できません。",
  "error.PROVIDER_RATE_LIMITED": "音声生成が一時的に制限されています。",
  "error.PROVIDER_AUTH_FAILED": "音声プロバイダが認証情報を拒否しました。",
  "error.PROVIDER_REQUEST_FAILED": "音声プロバイダが要求を処理できませんでした。",
  "error.AUDIO_PROCESSING_FAILED": "音声処理に失敗しました。",
  "error.STORAGE_FAILED": "生成した音声の保存に失敗しました。",
  "error.RENDER_CANCELLED": "生成がキャンセルされました。",
};

export const messages: Record<Locale, Record<MessageKey, string>> = { en, ja };
