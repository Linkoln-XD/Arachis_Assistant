import { useCallback, useEffect, useState } from "react";
import { api, asApiError, type ApiError } from "../api";
import { MeetingEditor, ReminderEditor, TaskEditor } from "../components/editors";
import { Banner, PageHeader, RawJson } from "../components/ui";
import { KIND, STATUS } from "../labels";
import { useSession } from "../session";
import { formatDateTime, formatDay, formatInterval, formatLongDay, shiftIsoDate, todayInZone } from "../time";
import type { CalendarItem, CalendarResponse, Meeting, Reminder, Task } from "../types";

type Editor =
  | { kind: "task"; item?: Task }
  | { kind: "meeting"; item?: Meeting }
  | { kind: "reminder"; item?: Reminder };

export function CalendarPage() {
  const session = useSession();
  const timeZone = session?.user.timezone ?? "Europe/Moscow";
  const [from, setFrom] = useState(() => todayInZone(timeZone));
  const [to, setTo] = useState(() => todayInZone(timeZone));
  const [kinds, setKinds] = useState({ task: true, meeting: true, reminder: true });
  const [data, setData] = useState<CalendarResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [filterNote, setFilterNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    const selected = (["task", "meeting", "reminder"] as const).filter((kind) => kinds[kind]);
    if (selected.length === 0) {
      setData(null);
      setError(null);
      setFilterNote("Отметьте хотя бы один вид записей.");
      return;
    }
    setFilterNote(null);
    setLoading(true);
    try {
      const types = selected.length === 3 ? undefined : selected.join(",");
      setData(await api.calendar(from, to, types));
      setError(null);
    } catch (caught) {
      setError(asApiError(caught));
    } finally {
      setLoading(false);
    }
  }, [from, to, kinds]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!session) return null;

  function move(days: number) {
    setFrom((value) => (value ? shiftIsoDate(value, days) : value));
    setTo((value) => (value ? shiftIsoDate(value, days) : value));
  }

  function handleSaved(message: string) {
    setEditor(null);
    setNotice(message);
    void load();
  }

  async function remove(item: CalendarItem) {
    if (!window.confirm(`Удалить «${itemTitle(item)}»?`)) return;
    setNotice(null);
    try {
      const key = crypto.randomUUID();
      if (item.type === "task") await api.deleteTask(item.id, key);
      else if (item.type === "meeting") await api.deleteMeeting(item.id, key);
      else await api.deleteReminder(item.id, key);
      setNotice("Запись удалена");
      await load();
    } catch (caught) {
      setError(asApiError(caught));
    }
  }

  async function complete(task: Task) {
    setNotice(null);
    try {
      const result = await api.completeTask(task.id);
      setNotice(result.status_changed ? "Задача выполнена" : "Задача уже была выполнена");
      await load();
    } catch (caught) {
      setError(asApiError(caught));
    }
  }

  async function reopen(task: Task) {
    setNotice(null);
    try {
      const result = await api.reopenTask(task.id);
      setNotice(result.status_changed ? "Задача снова активна" : "Задача уже была активна");
      await load();
    } catch (caught) {
      setError(asApiError(caught));
    }
  }

  const range =
    from && to ? (from === to ? formatLongDay(from) : `${formatLongDay(from)} — ${formatLongDay(to)}`) : "Укажите обе даты";

  return (
    <section>
      <PageHeader
        title="День"
        hint="Сводка за выбранные дни. Задача без срока сюда не попадает. Выполненные задачи и сработавшие напоминания остаются в списке."
        action={
          <div className="button-row">
            <button type="button" className="button" onClick={() => setEditor({ kind: "task" })}>
              Задача
            </button>
            <button type="button" className="button" onClick={() => setEditor({ kind: "meeting" })}>
              Встреча
            </button>
            <button type="button" className="button" onClick={() => setEditor({ kind: "reminder" })}>
              Напоминание
            </button>
          </div>
        }
      />
      <div className="toolbar">
        <button type="button" className="button ghost small" onClick={() => move(-1)} aria-label="Предыдущий день">
          ←
        </button>
        <button
          type="button"
          className="button ghost small"
          onClick={() => {
            const today = todayInZone(timeZone);
            setFrom(today);
            setTo(today);
          }}
        >
          Сегодня
        </button>
        <button type="button" className="button ghost small" onClick={() => move(1)} aria-label="Следующий день">
          →
        </button>
        <label className="field inline">
          <span>С</span>
          <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
        </label>
        <label className="field inline">
          <span>По</span>
          <input type="date" value={to} onChange={(event) => setTo(event.target.value)} />
        </label>
        {(["task", "meeting", "reminder"] as const).map((kind) => (
          <label key={kind} className="check">
            <input
              type="checkbox"
              checked={kinds[kind]}
              onChange={() => setKinds((current) => ({ ...current, [kind]: !current[kind] }))}
            />
            {KIND[kind]}
          </label>
        ))}
        {loading && <span className="loading">Обновляю…</span>}
      </div>
      <p className="range-label">{range}</p>
      {data && <p className="hint">Пояс ответа: {data.timezone}</p>}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {filterNote && <p className="empty">{filterNote}</p>}
      <Banner error={error} />
      <div className="agenda">
        {data?.items.map((item) => (
          <article key={`${item.type}-${item.id}`} className={isDone(item) ? "agenda-item done" : "agenda-item"}>
            <div>
              <p className="when">{when(item, timeZone)}</p>
              <span className={`kind ${item.type}`}>{KIND[item.type]}</span>
            </div>
            <div>
              <p className="item-title">{itemTitle(item)}</p>
              <p className="hint">{statusLine(item)}</p>
              <RawJson value={item} />
            </div>
            <div className="row-actions">
              {item.type === "task" && item.status === "active" && (
                <button type="button" className="text-button" onClick={() => void complete(item)}>
                  Выполнить
                </button>
              )}
              {item.type === "task" && item.status === "completed" && (
                <button type="button" className="text-button" onClick={() => void reopen(item)}>
                  Вернуть
                </button>
              )}
              <button type="button" className="text-button" onClick={() => edit(item)}>
                Изменить
              </button>
              <button type="button" className="text-button danger" onClick={() => void remove(item)}>
                Удалить
              </button>
            </div>
          </article>
        ))}
      </div>
      {data && data.items.length === 0 && !error && <p className="empty">В эти дни записей нет.</p>}
      {editor?.kind === "task" && (
        <TaskEditor
          key={editor.item?.id ?? "new-task"}
          task={editor.item}
          defaultDue={from}
          onClose={() => setEditor(null)}
          onSaved={handleSaved}
        />
      )}
      {editor?.kind === "meeting" && (
        <MeetingEditor
          key={editor.item?.id ?? "new-meeting"}
          meeting={editor.item}
          timeZone={timeZone}
          defaultDay={from || todayInZone(timeZone)}
          onClose={() => setEditor(null)}
          onSaved={handleSaved}
        />
      )}
      {editor?.kind === "reminder" && (
        <ReminderEditor
          key={editor.item?.id ?? "new-reminder"}
          reminder={editor.item}
          timeZone={timeZone}
          defaultDay={from || todayInZone(timeZone)}
          onClose={() => setEditor(null)}
          onSaved={handleSaved}
        />
      )}
    </section>
  );

  function edit(item: CalendarItem) {
    if (item.type === "task") setEditor({ kind: "task", item });
    else if (item.type === "meeting") setEditor({ kind: "meeting", item });
    else setEditor({ kind: "reminder", item });
  }
}

function itemTitle(item: CalendarItem): string {
  if (item.type === "task") return item.description;
  if (item.type === "meeting") return item.title;
  return item.text;
}

function when(item: CalendarItem, timeZone: string): string {
  if (item.type === "task") return item.due_on ? formatDay(item.due_on) : "без срока";
  if (item.type === "meeting") return formatInterval(item.starts_at, item.ends_at, timeZone);
  return formatDateTime(item.fire_at, timeZone);
}

function statusLine(item: CalendarItem): string {
  if (item.type === "task") return STATUS[item.status];
  if (item.type === "reminder") return STATUS[item.status];
  return "встреча";
}

function isDone(item: CalendarItem): boolean {
  return (item.type === "task" && item.status === "completed") || (item.type === "reminder" && item.status === "fired");
}
