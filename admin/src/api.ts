import type {
  CalendarResponse,
  Meeting,
  MeetingSaved,
  MeetingWrite,
  Page,
  Reminder,
  ReminderWrite,
  SessionResponse,
  Task,
  TaskStatusChange,
  TaskWrite,
  User,
} from "./types";

const STORAGE_KEY = "arachis.admin.session";

export type StoredSession = {
  accessToken: string;
  refreshToken: string;
  accessExpiresAt: number;
  user: User;
};

export type LogEntry = {
  id: number;
  at: string;
  method: string;
  path: string;
  status: number;
  ms: number;
  requestBody: unknown;
  responseBody: unknown;
  location: string | null;
};

export type FieldError = {
  field: string;
  code: string;
  message: string;
};

type SendOptions = {
  body?: unknown;
  auth?: boolean;
  idempotencyKey?: string;
  retry?: boolean;
  silent?: boolean;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown>) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  static fromBody(status: number, body: unknown): ApiError {
    if (!body || typeof body !== "object") return new ApiError(status, "error", "Ошибка", {});
    const record = body as { code?: unknown; message?: unknown; details?: unknown };
    const details =
      record.details && typeof record.details === "object" ? (record.details as Record<string, unknown>) : {};
    return new ApiError(
      status,
      typeof record.code === "string" ? record.code : "error",
      typeof record.message === "string" ? record.message : "Ошибка",
      details,
    );
  }

  fieldErrors(): FieldError[] {
    const raw = this.details.errors;
    if (!Array.isArray(raw)) return [];
    return raw.flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const record = item as { field?: unknown; code?: unknown; message?: unknown };
      return [
        {
          field: typeof record.field === "string" ? record.field : "",
          code: typeof record.code === "string" ? record.code : "",
          message: typeof record.message === "string" ? record.message : "",
        },
      ];
    });
  }

  conflicts(): Meeting[] {
    const raw = this.details.conflicts;
    if (!Array.isArray(raw)) return [];
    return raw.filter(isMeeting);
  }
}

export function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError(0, "error", "Ошибка", {});
}

function isMeeting(value: unknown): value is Meeting {
  if (!value || typeof value !== "object") return false;
  const record = value as Meeting;
  return record.type === "meeting" && typeof record.id === "string" && typeof record.starts_at === "string";
}

export function apiBase(): string {
  const configured = import.meta.env.VITE_API_BASE?.trim();
  const base = configured || "http://127.0.0.1:8000/api/v1";
  return base.replace(/\/$/, "");
}

export function apiOrigin(): string {
  return apiBase().replace(/\/api\/v1$/, "");
}

let session: StoredSession | null = readStored();
const sessionListeners = new Set<() => void>();

let entries: LogEntry[] = [];
let nextLogId = 1;
const logListeners = new Set<() => void>();
let refreshTask: Promise<void> | null = null;

export function getSession(): StoredSession | null {
  return session;
}

export function subscribeSession(listener: () => void): () => void {
  sessionListeners.add(listener);
  return () => sessionListeners.delete(listener);
}

export function getLog(): LogEntry[] {
  return entries;
}

export function subscribeLog(listener: () => void): () => void {
  logListeners.add(listener);
  return () => logListeners.delete(listener);
}

export function clearLog(): void {
  entries = [];
  logListeners.forEach((listener) => listener());
}

function setSession(next: StoredSession | null): void {
  session = next;
  if (next) localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  else localStorage.removeItem(STORAGE_KEY);
  sessionListeners.forEach((listener) => listener());
}

function readStored(): StoredSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredSession;
    if (!parsed.accessToken || !parsed.refreshToken || !parsed.user?.email) return null;
    return parsed;
  } catch {
    return null;
  }
}

function saveIssued(body: SessionResponse): void {
  setSession({
    accessToken: body.access_token,
    refreshToken: body.refresh_token,
    accessExpiresAt: Date.now() + body.expires_in * 1000,
    user: body.user,
  });
}

function rememberUser(user: User): void {
  if (!session) return;
  setSession({ ...session, user });
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

function redact(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redact);
  if (!value || typeof value !== "object") return value;
  const copy: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    copy[key] = key === "password" || key === "access_token" || key === "refresh_token" ? "•••" : redact(item);
  }
  return copy;
}

function pushLog(entry: LogEntry): void {
  entries = [entry, ...entries].slice(0, 40);
  logListeners.forEach((listener) => listener());
}

async function parseJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

async function ensureFresh(): Promise<void> {
  const current = getSession();
  if (!current) return;
  if (current.accessExpiresAt - Date.now() > 30_000) return;
  await refresh();
}

function refresh(): Promise<void> {
  if (!refreshTask) {
    refreshTask = refreshOnce().finally(() => {
      refreshTask = null;
    });
  }
  return refreshTask;
}

async function refreshOnce(): Promise<void> {
  const current = getSession();
  if (!current) throw new ApiError(401, "invalid_refresh", "Нужно войти снова", {});
  let response: Response;
  try {
    response = await fetch(`${apiBase()}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: current.refreshToken }),
    });
  } catch {
    throw new ApiError(0, "network", "Сервер недоступен", {});
  }
  const body = await parseJson(response);
  if (!response.ok) {
    setSession(null);
    throw ApiError.fromBody(response.status, body);
  }
  saveIssued(body as SessionResponse);
}

async function send<T>(method: string, path: string, options: SendOptions = {}): Promise<T> {
  if (options.auth !== false) await ensureFresh();
  const current = options.auth === false ? null : getSession();
  if (options.auth !== false && !current) throw new ApiError(401, "unauthorized", "Нужна авторизация", {});

  const started = performance.now();
  let response: Response;
  try {
    response = await fetch(`${apiBase()}${path}`, {
      method,
      headers: {
        ...(options.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(current ? { Authorization: `Bearer ${current.accessToken}` } : {}),
        ...(options.idempotencyKey ? { "Idempotency-Key": options.idempotencyKey } : {}),
      },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    if (!options.silent) {
      pushLog({
        id: nextLogId++,
        at: new Date().toISOString(),
        method,
        path,
        status: 0,
        ms: Math.round(performance.now() - started),
        requestBody: redact(options.body ?? null),
        responseBody: null,
        location: null,
      });
    }
    throw new ApiError(0, "network", "Сервер недоступен", {});
  }

  if (response.status === 401 && options.auth !== false && options.retry !== false) {
    const errorBody = await parseJson(response);
    if (!options.silent) record(method, path, response, started, options.body, errorBody);
    const error = ApiError.fromBody(response.status, errorBody);
    if (error.code === "token_expired") {
      await refresh();
      return send(method, path, { ...options, retry: false });
    }
    if (error.code === "invalid_refresh" || error.code === "unauthorized") setSession(null);
    throw error;
  }

  const body = response.status === 204 ? null : await parseJson(response);
  if (!options.silent) record(method, path, response, started, options.body, body);
  if (!response.ok) throw ApiError.fromBody(response.status, body);
  return body as T;
}

function record(
  method: string,
  path: string,
  response: Response,
  started: number,
  requestBody: unknown,
  responseBody: unknown,
): void {
  pushLog({
    id: nextLogId++,
    at: new Date().toISOString(),
    method,
    path,
    status: response.status,
    ms: Math.round(performance.now() - started),
    requestBody: redact(requestBody ?? null),
    responseBody: redact(responseBody),
    location: response.headers.get("Location"),
  });
}

export const api = {
  health: () => send<{ status: string }>("GET", "/health", { auth: false, silent: true }),

  register: async (email: string, password: string, timezone: string) => {
    saveIssued(
      await send<SessionResponse>("POST", "/auth/register", {
        auth: false,
        body: { email, password, timezone },
      }),
    );
  },

  login: async (email: string, password: string) => {
    saveIssued(
      await send<SessionResponse>("POST", "/auth/login", {
        auth: false,
        body: { email, password },
      }),
    );
  },

  logout: async () => {
    const token = getSession()?.refreshToken;
    setSession(null);
    if (!token) return;
    await send("POST", "/auth/logout", { auth: false, body: { refresh_token: token } }).catch(() => undefined);
  },

  me: async () => {
    const user = await send<User>("GET", "/auth/me");
    rememberUser(user);
    return user;
  },

  patchTimezone: async (timezone: string) => {
    const user = await send<User>("PATCH", "/auth/me", { body: { timezone } });
    rememberUser(user);
    return user;
  },

  listTasks: (params: { status: string; due: string; from: string; to: string; limit: number; offset: number }) =>
    send<Page<Task>>(
      "GET",
      `/tasks${query({
        status: params.status,
        due: params.due,
        from: params.from,
        to: params.to,
        limit: params.limit,
        offset: params.offset,
      })}`,
    ),

  createTask: (body: TaskWrite, idempotencyKey: string) =>
    send<Task>("POST", "/tasks", { body, idempotencyKey }),

  updateTask: (id: string, body: TaskWrite) => send<Task>("PATCH", `/tasks/${id}`, { body }),

  completeTask: (id: string) => send<TaskStatusChange>("POST", `/tasks/${id}/complete`),

  reopenTask: (id: string) => send<TaskStatusChange>("POST", `/tasks/${id}/reopen`),

  deleteTask: (id: string, idempotencyKey: string) =>
    send<void>("DELETE", `/tasks/${id}`, { idempotencyKey }),

  listMeetings: (params: { from: string; to: string; limit: number; offset: number }) =>
    send<Page<Meeting>>(
      "GET",
      `/meetings${query({
        from: params.from,
        to: params.to,
        limit: params.limit,
        offset: params.offset,
      })}`,
    ),

  createMeeting: (body: MeetingWrite, idempotencyKey: string) =>
    send<MeetingSaved>("POST", "/meetings", { body, idempotencyKey }),

  updateMeeting: (id: string, body: MeetingWrite) => send<MeetingSaved>("PATCH", `/meetings/${id}`, { body }),

  deleteMeeting: (id: string, idempotencyKey: string) =>
    send<void>("DELETE", `/meetings/${id}`, { idempotencyKey }),

  listReminders: (params: { status: string; from: string; to: string; limit: number; offset: number }) =>
    send<Page<Reminder>>(
      "GET",
      `/reminders${query({
        status: params.status,
        from: params.from,
        to: params.to,
        limit: params.limit,
        offset: params.offset,
      })}`,
    ),

  createReminder: (body: ReminderWrite, idempotencyKey: string) =>
    send<Reminder>("POST", "/reminders", { body, idempotencyKey }),

  updateReminder: (id: string, body: ReminderWrite) => send<Reminder>("PATCH", `/reminders/${id}`, { body }),

  deleteReminder: (id: string, idempotencyKey: string) =>
    send<void>("DELETE", `/reminders/${id}`, { idempotencyKey }),

  calendar: (dateFrom: string, dateTo: string, types?: string) =>
    send<CalendarResponse>("GET", `/calendar${query({ from: dateFrom, to: dateTo, types })}`),
};
