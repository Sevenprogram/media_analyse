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

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
  } catch {
    throw new ApiError("无法连接后端服务，请确认 8000 服务正在运行。", "network");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(body.detail || `HTTP ${response.status}`, "http", response.status);
  }
  return response.json() as Promise<T>;
}
