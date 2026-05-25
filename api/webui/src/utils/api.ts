import { clearAuthSession, getStoredAuthSession } from "./authSession";

export class ApiError extends Error {
  status?: number;
  kind: "http" | "network";

  constructor(message: string, kind: "http" | "network", status?: number) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
}

function formatApiErrorDetail(detail: unknown): string {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const record = detail as { message?: unknown; code?: unknown };
    if (typeof record.message === "string" && record.message.trim()) {
      return record.message;
    }
    if (typeof record.code === "string" && record.code.trim()) {
      return record.code;
    }
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== "object") return null;
        const record = item as { msg?: unknown; loc?: unknown };
        const message = typeof record.msg === "string" ? record.msg : null;
        const location = Array.isArray(record.loc)
          ? record.loc
              .filter((part) => typeof part === "string" || typeof part === "number")
              .join(".")
          : null;
        if (message && location) return `${location}: ${message}`;
        return message;
      })
      .filter((message): message is string => Boolean(message));
    if (messages.length > 0) {
      return messages.join("; ");
    }
  }
  return "请求失败，请检查输入参数后重试。";
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  const headers = new Headers(options.headers || {});
  const session = getStoredAuthSession();

  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (session?.accessToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${session.accessToken}`);
  }

  try {
    response = await fetch(path, {
      ...options,
      headers,
    });
  } catch (error) {
    if ((error as Error | undefined)?.name === "AbortError") {
      throw error;
    }
    throw new ApiError("无法连接后端服务，请确认 8000 服务正在运行。", "network");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    if (response.status === 401 && !path.startsWith("/api/auth/")) {
      clearAuthSession();
      window.dispatchEvent(new Event("auth:unauthorized"));
    }
    throw new ApiError(formatApiErrorDetail(body.detail) || `HTTP ${response.status}`, "http", response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}
