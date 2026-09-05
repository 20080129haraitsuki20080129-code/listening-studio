-- Listening Studio PostgreSQL schema
-- UUID extension may vary by environment.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('monologue', 'dialogue', 'listening_test', 'shadowing')),
    source_text TEXT NOT NULL DEFAULT '',
    transcript_visible_default BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE voices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    provider TEXT NOT NULL CHECK (provider IN ('openai', 'azure', 'elevenlabs')),
    provider_voice_id TEXT NOT NULL,
    provider_model_hint TEXT,

    name TEXT NOT NULL,

    language TEXT NOT NULL DEFAULT 'en',
    locale TEXT,

    accent TEXT,
    gender TEXT NOT NULL DEFAULT 'unknown'
        CHECK (gender IN ('female', 'male', 'neutral', 'unknown')),
    age_group TEXT NOT NULL DEFAULT 'unknown'
        CHECK (age_group IN ('young', 'adult', 'mature', 'unknown')),

    style_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    preview_url TEXT,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(provider, provider_voice_id)
);

CREATE INDEX idx_voices_provider ON voices(provider);
CREATE INDEX idx_voices_language ON voices(language);
CREATE INDEX idx_voices_locale ON voices(locale);
CREATE INDEX idx_voices_accent ON voices(accent);
CREATE INDEX idx_voices_gender ON voices(gender);
CREATE INDEX idx_voices_enabled ON voices(enabled);

CREATE TABLE speakers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    label TEXT NOT NULL,
    display_name TEXT NOT NULL,

    voice_id UUID REFERENCES voices(id),

    generation_speed NUMERIC(6,3) NOT NULL DEFAULT 1.0,
    default_pause_before_ms INTEGER NOT NULL DEFAULT 0 CHECK (default_pause_before_ms >= 0),
    default_pause_after_ms INTEGER NOT NULL DEFAULT 250 CHECK (default_pause_after_ms >= 0),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(project_id, label)
);

CREATE TABLE audio_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    storage_key TEXT NOT NULL UNIQUE,

    mime_type TEXT NOT NULL,
    format TEXT NOT NULL CHECK (format IN ('mp3', 'wav', 'opus', 'aac', 'flac', 'pcm')),

    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),

    sha256 TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audio_assets_sha256 ON audio_assets(sha256);

CREATE TABLE segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    order_index INTEGER NOT NULL CHECK (order_index >= 0),

    speaker_id UUID REFERENCES speakers(id) ON DELETE SET NULL,

    text TEXT NOT NULL,

    voice_id_override UUID REFERENCES voices(id),
    generation_speed_override NUMERIC(6,3),

    pause_before_ms INTEGER NOT NULL DEFAULT 0 CHECK (pause_before_ms >= 0),
    pause_after_ms INTEGER NOT NULL DEFAULT 250 CHECK (pause_after_ms >= 0),

    audio_asset_id UUID REFERENCES audio_assets(id) ON DELETE SET NULL,
    duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(project_id, order_index)
);

CREATE INDEX idx_segments_project_order ON segments(project_id, order_index);
CREATE INDEX idx_segments_speaker ON segments(speaker_id);

CREATE TABLE render_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),

    progress INTEGER NOT NULL DEFAULT 0
        CHECK (progress >= 0 AND progress <= 100),

    output_format TEXT NOT NULL DEFAULT 'mp3'
        CHECK (output_format IN ('mp3', 'wav', 'opus', 'aac', 'flac')),

    final_audio_asset_id UUID REFERENCES audio_assets(id) ON DELETE SET NULL,

    error_code TEXT,
    error_message TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE INDEX idx_render_jobs_project ON render_jobs(project_id);
CREATE INDEX idx_render_jobs_status ON render_jobs(status);

CREATE TABLE tts_cache (
    cache_key TEXT PRIMARY KEY,

    provider TEXT NOT NULL,
    model TEXT,
    provider_voice_id TEXT NOT NULL,

    normalized_text_hash TEXT NOT NULL,

    speed NUMERIC(6,3) NOT NULL,
    output_format TEXT NOT NULL,

    audio_asset_id UUID NOT NULL REFERENCES audio_assets(id) ON DELETE CASCADE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tts_cache_last_used ON tts_cache(last_used_at);
