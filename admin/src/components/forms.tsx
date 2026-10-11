import { useState, type FormEvent } from "react";
import type { Meeting, MeetingWrite, Reminder, ReminderWrite, Task, TaskWrite } from "../types";
import { defaultStart, isoToWall, wallTimeToIso } from "../time";

function resolveKey(value: string): string {
  const trimmed = value.trim();
  return trimmed || crypto.randomUUID();
}

function FormActions({ pending, label, onCancel }: { pending: boolean; label: string; onCancel: () => void }) {
  return (
    <div className="form-actions">
      <button type="submit" className="button" disabled={pending}>
        {pending ? "Сохраняю…" : label}
      </button>
      <button type="button" className="button ghost" onClick={onCancel} disabled={pending}>
        Отмена
      </button>
    </div>
  );
}

function IdempotencyField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <details className="advanced">
      <summary>Ключ идемпотентности</summary>
      <label className="field">
        <span>Тот же ключ и то же тело повторяют прошлый ответ. Другое тело отвечает 409.</span>
        <input value={value} onChange={(event) => onChange(event.target.value)} spellCheck={false} autoComplete="off" />
      </label>
    </details>
  );
}

export function TaskForm({
  task,
  defaultDue,
  pending,
  onSubmit,
  onCancel,
}: {
  task?: Task;
  defaultDue?: string;
  pending: boolean;
  onSubmit: (body: TaskWrite, idempotencyKey?: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [description, setDescription] = useState(task?.description ?? "");
  const [dueOn, setDueOn] = useState(task?.due_on ?? (task ? "" : defaultDue ?? ""));
  const [idempotencyKey, setIdempotencyKey] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!task) {
      const body: TaskWrite = { description };
      if (dueOn) body.due_on = dueOn;
      void onSubmit(body, resolveKey(idempotencyKey));
      return;
    }
    const body: TaskWrite = {};
    if (description !== task.description) body.description = description;
    if (dueOn !== (task.due_on ?? "")) body.due_on = dueOn || null;
    void onSubmit(body);
  }

  return (
    <form className="form" onSubmit={handleSubmit}>
      <label className="field">
        <span>Описание</span>
        <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} autoFocus />
      </label>
      <label className="field">
        <span>Срок</span>
        <input type="date" value={dueOn} onChange={(event) => setDueOn(event.target.value)} />
      </label>
      <p className="hint">Пустой срок сохраняет задачу без даты. Прошедшая дата отвечает in_the_past. Сегодня можно.</p>
      {!task && <IdempotencyField value={idempotencyKey} onChange={setIdempotencyKey} />}
      <FormActions pending={pending} label={task ? "Сохранить" : "Создать"} onCancel={onCancel} />
    </form>
  );
}

export function MeetingForm({
  meeting,
  timeZone,
  defaultDay,
  pending,
  onSubmit,
  onCancel,
}: {
  meeting?: Meeting;
  timeZone: string;
  defaultDay: string;
  pending: boolean;
  onSubmit: (body: MeetingWrite, idempotencyKey?: string) => Promise<void>;
  onCancel: () => void;
}) {
  const initialStart = meeting ? isoToWall(meeting.starts_at, timeZone) : defaultStart(defaultDay, timeZone);
  const initialEnd = meeting ? isoToWall(meeting.ends_at, timeZone) : { date: "", time: "" };
  const [title, setTitle] = useState(meeting?.title ?? "");
  const [startDate, setStartDate] = useState(initialStart.date);
  const [startTime, setStartTime] = useState(initialStart.time);
  const [endDate, setEndDate] = useState(initialEnd.date);
  const [endTime, setEndTime] = useState(initialEnd.time);
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [hint, setHint] = useState<string | null>(null);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const body: MeetingWrite = {};
    let note: string | null = null;
    if (!meeting || title !== meeting.title) body.title = title;
    const startChanged = startDate !== initialStart.date || startTime !== initialStart.time;
    if (startDate && startTime) {
      if (!meeting || startChanged) body.starts_at = wallTimeToIso(startDate, startTime, timeZone);
    } else if (startDate || startTime) {
      note = "Начало не отправлено: нужны и дата, и время.";
    }
    const endChanged = endDate !== initialEnd.date || endTime !== initialEnd.time;
    if (endDate && endTime) {
      if (!meeting || endChanged) body.ends_at = wallTimeToIso(endDate, endTime, timeZone);
    } else if (endDate || endTime) {
      note = "Конец не отправлен: нужны и дата, и время.";
    } else if (meeting && endChanged) {
      note = "Прежний конец сохранится: у встречи нельзя убрать время окончания.";
    }
    setHint(note);
    void onSubmit(body, meeting ? undefined : resolveKey(idempotencyKey));
  }

  return (
    <form className="form" onSubmit={handleSubmit}>
      <label className="field">
        <span>Название</span>
        <input value={title} onChange={(event) => setTitle(event.target.value)} autoFocus />
      </label>
      <div className="split">
        <label className="field">
          <span>Начало, дата</span>
          <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        </label>
        <label className="field">
          <span>Начало, время</span>
          <input type="time" value={startTime} onChange={(event) => setStartTime(event.target.value)} />
        </label>
      </div>
      <div className="split">
        <label className="field">
          <span>Конец, дата</span>
          <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
        </label>
        <label className="field">
          <span>Конец, время</span>
          <input type="time" value={endTime} onChange={(event) => setEndTime(event.target.value)} />
        </label>
      </div>
      <p className="hint">
        Пустой конец при создании даёт встречу на час. Если менять только начало, длительность сохраняется. Правка одного
        названия пересечение не проверяет.
      </p>
      {hint && <p className="hint">{hint}</p>}
      {!meeting && <IdempotencyField value={idempotencyKey} onChange={setIdempotencyKey} />}
      <FormActions pending={pending} label={meeting ? "Сохранить" : "Создать"} onCancel={onCancel} />
    </form>
  );
}

export function ReminderForm({
  reminder,
  timeZone,
  defaultDay,
  pending,
  onSubmit,
  onCancel,
}: {
  reminder?: Reminder;
  timeZone: string;
  defaultDay: string;
  pending: boolean;
  onSubmit: (body: ReminderWrite, idempotencyKey?: string) => Promise<void>;
  onCancel: () => void;
}) {
  const initialWall = reminder ? isoToWall(reminder.fire_at, timeZone) : defaultStart(defaultDay, timeZone);
  const [text, setText] = useState(reminder?.text ?? "");
  const [date, setDate] = useState(initialWall.date);
  const [time, setTime] = useState(initialWall.time);
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [hint, setHint] = useState<string | null>(null);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const body: ReminderWrite = {};
    let note: string | null = null;
    if (!reminder || text !== reminder.text) body.text = text;
    const changed = date !== initialWall.date || time !== initialWall.time;
    if (date && time) {
      if (!reminder || changed) body.fire_at = wallTimeToIso(date, time, timeZone);
    } else if (date || time || !reminder) {
      note = "Момент не отправлен: нужны и дата, и время.";
    }
    setHint(note);
    void onSubmit(body, reminder ? undefined : resolveKey(idempotencyKey));
  }

  return (
    <form className="form" onSubmit={handleSubmit}>
      <label className="field">
        <span>Текст</span>
        <textarea value={text} onChange={(event) => setText(event.target.value)} rows={3} autoFocus />
      </label>
      <div className="split">
        <label className="field">
          <span>Когда, дата</span>
          <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        </label>
        <label className="field">
          <span>Когда, время</span>
          <input type="time" value={time} onChange={(event) => setTime(event.target.value)} />
        </label>
      </div>
      <p className="hint">Прошедший момент отвечает in_the_past. Уведомление пока не отправляется.</p>
      {reminder?.status === "fired" && (
        <p className="hint">Новое время в будущем вернёт статус в «ждёт». Правка только текста статус не меняет.</p>
      )}
      {hint && <p className="hint">{hint}</p>}
      {!reminder && <IdempotencyField value={idempotencyKey} onChange={setIdempotencyKey} />}
      <FormActions pending={pending} label={reminder ? "Сохранить" : "Создать"} onCancel={onCancel} />
    </form>
  );
}
