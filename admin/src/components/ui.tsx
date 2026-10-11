import { useEffect, type ReactNode } from "react";
import { ApiError } from "../api";
import type { Meeting } from "../types";
import { formatInterval } from "../time";

export function PageHeader({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  useEffect(() => {
    document.title = `${title} · Арахис`;
  }, [title]);

  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {hint && <p className="lede">{hint}</p>}
      </div>
      {action}
    </header>
  );
}

export function Banner({ error }: { error: ApiError | null }) {
  if (!error) return null;
  const fields = error.fieldErrors();
  const field = typeof error.details.field === "string" ? error.details.field : null;
  return (
    <div className="banner" role="alert">
      <p className="banner-code">
        <strong>{error.status > 0 ? error.status : error.code === "network" ? "сеть" : "—"}</strong>
        <code>{error.code}</code>
      </p>
      <p>{error.message}</p>
      {field && (
        <p>
          Поле <code>{field}</code>
        </p>
      )}
      {fields.length > 0 && (
        <ul>
          {fields.map((item) => (
            <li key={`${item.field}-${item.code}`}>
              <code>{item.field}</code> {item.code}
              {item.message ? ` — ${item.message}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Modal({
  title,
  onClose,
  children,
  front = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  front?: boolean;
}) {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className={front ? "modal-backdrop front" : "modal-backdrop"} onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <h2>{title}</h2>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Закрыть">
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function DateFields({
  from,
  to,
  onFrom,
  onTo,
}: {
  from: string;
  to: string;
  onFrom: (value: string) => void;
  onTo: (value: string) => void;
}) {
  return (
    <>
      <label className="field inline">
        <span>С</span>
        <input type="date" value={from} onChange={(event) => onFrom(event.target.value)} />
      </label>
      <label className="field inline">
        <span>По</span>
        <input type="date" value={to} onChange={(event) => onTo(event.target.value)} />
      </label>
    </>
  );
}

export function Pager({
  offset,
  limit,
  total,
  onOffset,
}: {
  offset: number;
  limit: number;
  total: number;
  onOffset: (offset: number) => void;
}) {
  const shown = total === 0 ? "0 записей" : `${offset + 1}–${Math.min(offset + limit, total)} из ${total}`;
  return (
    <div className="pager">
      <button type="button" className="button ghost small" disabled={offset === 0} onClick={() => onOffset(Math.max(0, offset - limit))}>
        Назад
      </button>
      <span>{shown}</span>
      <button
        type="button"
        className="button ghost small"
        disabled={offset + limit >= total}
        onClick={() => onOffset(offset + limit)}
      >
        Дальше
      </button>
    </div>
  );
}

export function OverlapDialog({
  message,
  conflicts,
  timeZone,
  pending,
  onCancel,
  onConfirm,
}: {
  message: string;
  conflicts: Meeting[];
  timeZone: string;
  pending: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Modal title="На это время уже есть встреча" onClose={onCancel} front>
      <p>{message}</p>
      <p className="hint">
        Сервер ничего не записал. Повтор уйдёт с новым ключом идемпотентности: тело другое, в нём{" "}
        <code>allow_overlap: true</code>.
      </p>
      {conflicts.length > 0 && (
        <ul className="conflicts">
          {conflicts.map((meeting) => (
            <li key={meeting.id}>
              <strong>{meeting.title}</strong>
              <span>{formatInterval(meeting.starts_at, meeting.ends_at, timeZone)}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="form-actions">
        <button type="button" className="button" disabled={pending} onClick={onConfirm}>
          {pending ? "Сохраняю…" : "Поставить параллельно"}
        </button>
        <button type="button" className="button ghost" disabled={pending} onClick={onCancel}>
          Отмена
        </button>
      </div>
    </Modal>
  );
}

export function RawJson({ value }: { value: unknown }) {
  return (
    <details className="raw">
      <summary>JSON</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
