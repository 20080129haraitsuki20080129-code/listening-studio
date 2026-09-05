import type {
  AuthStatus,
  Project,
  ProjectSummary,
  RenderJob,
  Segment,
  Speaker,
  SpeedLevel,
  Voice,
} from "./types";

const BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

/** An error the API returned in its normalized envelope. */
export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly retryable: boolean,
    readonly requestId: string | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      // The session is an httpOnly cookie the page cannot read, so it has to
      // ride along on every request -- including cross-origin ones.
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    });
  } catch {
    throw new ApiError(
      "NETWORK_ERROR",
      "Could not reach the server. Is the backend running?",
      true,
      null,
    );
  }

  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body?.error;
    throw new ApiError(
      error?.code ?? "REQUEST_FAILED",
      error?.message ?? `Request failed (${response.status}).`,
      error?.retryable ?? false,
      error?.request_id ?? null,
    );
  }
  return body as T;
}

/** Absolute URL for an audio path the API returned. */
export function audioUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  return `${BASE.replace(/\/api\/v1$/, "")}${path}`;
}

/** Absolute URLs for the download endpoints. */
export const downloadUrls = {
  audio: (renderId: string) => `${BASE}/renders/${renderId}/download`,
  transcript: (projectId: string) => `${BASE}/projects/${projectId}/transcript.pdf`,
};

/** Where the browser is sent to start a provider sign-in. */
export function loginUrl(provider: string): string {
  return `${BASE}/auth/${provider}/login`;
}

export const api = {
  authStatus: () => request<AuthStatus>("/auth/status"),
  logout: () => request<void>("/auth/logout", { method: "POST" }),

  health: () => request<{ status: string }>("/health"),

  listVoices: (params: Record<string, string> = {}) => {
    const query = new URLSearchParams(params).toString();
    return request<{ items: Voice[] }>(`/voices${query ? `?${query}` : ""}`);
  },
  syncVoices: () =>
    request<{ created: number; updated: number; providers: string[] }>(
      "/voices/sync",
      { method: "POST" },
    ),

  speedLevels: () =>
    request<{ items: SpeedLevel[]; default_level: number }>("/speed-levels"),

  listProjects: () => request<ProjectSummary[]>("/projects"),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  createProject: (body: { title: string; mode: string; source_text?: string }) =>
    request<Project>("/projects", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateProject: (id: string, body: Record<string, unknown>) =>
    request<Project>(`/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteProject: (id: string) =>
    request<void>(`/projects/${id}`, { method: "DELETE" }),

  parseProject: (id: string, body: { source_text?: string; mode?: string }) =>
    request<{ speakers: { label: string }[] }>(`/projects/${id}/parse`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  setSpeakerCount: (projectId: string, count: number) =>
    request<Speaker[]>(`/projects/${projectId}/speakers`, {
      method: "PUT",
      body: JSON.stringify({ count }),
    }),

  updateSpeaker: (id: string, body: Record<string, unknown>) =>
    request<Speaker>(`/speakers/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  updateSegment: (id: string, body: Record<string, unknown>) =>
    request<Segment>(`/segments/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  renderSegment: (id: string) =>
    request<{ audio_asset_id: string; audio_url: string; duration_ms: number }>(
      `/segments/${id}/render`,
      { method: "POST" },
    ),

  createRender: (projectId: string, format = "mp3", idempotencyKey?: string) =>
    request<RenderJob>(`/projects/${projectId}/renders`, {
      method: "POST",
      body: JSON.stringify({ format }),
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
    }),
  getRender: (id: string) => request<RenderJob>(`/renders/${id}`),
  cancelRender: (id: string) =>
    request<RenderJob>(`/renders/${id}/cancel`, { method: "POST" }),
};
