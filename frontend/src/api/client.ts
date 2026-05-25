import type { ClientErrorSource, NormalizedClientError } from "../types/api";

type JsonObject = Record<string, unknown>;

export class GatewayClientError extends Error {
  readonly detail: NormalizedClientError;

  constructor(detail: NormalizedClientError) {
    super(detail.message);
    this.name = "GatewayClientError";
    this.detail = detail;
  }
}

export type GatewayClientConfig = {
  baseUrl?: string;
  apiKey?: string;
  fetchImpl?: typeof fetch;
};

export class GatewayHttpClient {
  private readonly baseUrl: string;
  private readonly apiKey?: string;
  private readonly fetchImpl: typeof fetch;

  constructor(config: GatewayClientConfig = {}) {
    this.baseUrl = normalizeBaseUrl(config.baseUrl ?? import.meta.env.VITE_OHMATIC_API_BASE_URL ?? "");
    this.apiKey = config.apiKey ?? import.meta.env.VITE_OHMATIC_API_KEY;
    this.fetchImpl = config.fetchImpl ?? fetch;
  }

  async get<T>(path: string, source: ClientErrorSource): Promise<T> {
    return this.request<T>(path, { method: "GET" }, source);
  }

  async post<T>(path: string, body: unknown, source: ClientErrorSource): Promise<T> {
    return this.request<T>(
      path,
      {
        method: "POST",
        body: JSON.stringify(body)
      },
      source
    );
  }

  private async request<T>(path: string, init: RequestInit, source: ClientErrorSource): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (init.body) {
      headers.set("Content-Type", "application/json");
    }
    if (this.apiKey) {
      // BACKEND ENTRY: future OHMATIC_MODE=server auth hooks in here.
      // Local mode should leave VITE_OHMATIC_API_KEY unset.
      headers.set("Authorization", `Bearer ${this.apiKey}`);
    }

    const response = await this.fetchImpl(toUrl(this.baseUrl, path), {
      ...init,
      headers
    });

    const payload = await readJson(response);
    if (!response.ok) {
      throw new GatewayClientError(normalizeHttpError(response.status, payload, source));
    }

    return payload as T;
  }
}

export function normalizeHttpError(
  httpStatus: number,
  payload: unknown,
  source: ClientErrorSource
): NormalizedClientError {
  if (isJsonObject(payload) && typeof payload.error === "string") {
    return {
      code: codeFromFlatError(payload.error, httpStatus),
      message: payload.error,
      httpStatus,
      source
    };
  }

  return {
    code: httpStatus === 503 ? "inference_unavailable" : `http_${httpStatus}`,
    message: `Gateway returned HTTP ${httpStatus}`,
    httpStatus,
    source
  };
}

export function normalizeJobError(error: { code?: unknown; message?: unknown }): NormalizedClientError {
  return {
    code: typeof error.code === "string" ? error.code : "job_failed",
    message: typeof error.message === "string" ? error.message : "Generation job failed",
    source: "job"
  };
}

function codeFromFlatError(message: string, httpStatus: number): string {
  if (/^[a-z0-9_]+$/.test(message)) {
    return message;
  }
  if (httpStatus === 503) {
    return "inference_unavailable";
  }
  return `http_${httpStatus}`;
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return {};
  }

  try {
    return JSON.parse(text) as unknown;
  } catch {
    return { error: text };
  }
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/$/, "");
}

function toUrl(baseUrl: string, path: string): string {
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  return `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
