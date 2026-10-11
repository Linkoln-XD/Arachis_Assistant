import { useEffect, useState } from "react";
import { api, asApiError, type ApiError } from "../api";
import { ReminderEditor } from "../components/editors";
import { Banner, DateFields, PageHeader, Pager, RawJson } from "../components/ui";
import { STATUS } from "../labels";
import { useSession } from "../session";
import { formatDateTime, todayInZone } from "../time";
import type { Page, Reminder } from "../types";

const limit = 50;

export function RemindersPage() {
  const session = useSession();
  const timeZone = session?.user.timezone ?? "Europe/Moscow";
  const [status, setStatus] = useState("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<Page<Reminder> | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [editor, setEditor] = useState<Reminder | "new" | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    setLoading(true);
    api
      .listReminders({ status, from, to, limit, offset })
      .then((result) => {
        if (!cancelled) {
          setPage(result);
          setError(null);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(asApiError(caught));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, status, from, to, offset, timeZone, version]);

  if (!session) return null;

  function handleSaved(message: string) {
    setEditor(null);
    setNotice(message);
    setOffset(0);
    setVersion((value) => value + 1);
  }

  async function remove(reminder: Reminder) {
    if (!window.confirm(`Удалить «${reminder.text}»?`)) return;
    setNotice(null);
    try {
      await api.deleteReminder(reminder.id, crypto.randomUUID());
      setNotice("Напоминание удалено");
      setVersion((value) => value + 1);
    } catch (caught) {
      setError(asApiError(caught));
    }
  }

  return (
    <section>
      <PageHeader
        title="Напоминания"
        hint="Здесь видна только запись. Отдельного уведомления в приложении пока нет. Сработавшие можно вернуть в ожидание, сдвинув момент в будущее."
        action={
          <button type="button" className="button" onClick={() => setEditor("new")}>
            Новое напоминание
          </button>
        }
      />
      <div className="toolbar">
        <label className="field inline">
          <span>Статус</span>
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setOffset(0);
            }}
          >
            <option value="all">все</option>
            <option value="pending">ждут</option>
            <option value="fired">сработавшие</option>
          </select>
        </label>
        <DateFields
          from={from}
          to={to}
          onFrom={(value) => {
            setFrom(value);
            setOffset(0);
          }}
          onTo={(value) => {
            setTo(value);
            setOffset(0);
          }}
        />
        {loading && <span className="loading">Обновляю…</span>}
      </div>
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      <Banner error={error} />
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Текст</th>
              <th>Когда</th>
              <th>Статус</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {page?.items.map((reminder) => (
              <tr key={reminder.id} className={reminder.status === "fired" ? "done" : undefined}>
                <td>
                  <p className="item-title">{reminder.text}</p>
                  <RawJson value={reminder} />
                </td>
                <td>{formatDateTime(reminder.fire_at, timeZone)}</td>
                <td>{STATUS[reminder.status]}</td>
                <td>
                  <div className="row-actions">
                    <button type="button" className="text-button" onClick={() => setEditor(reminder)}>
                      Изменить
                    </button>
                    <button type="button" className="text-button danger" onClick={() => void remove(reminder)}>
                      Удалить
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {page && page.items.length === 0 && !error && <p className="empty">Напоминаний нет.</p>}
      {page && <Pager offset={page.offset} limit={page.limit} total={page.total} onOffset={setOffset} />}
      {editor && (
        <ReminderEditor
          key={editor === "new" ? "new" : editor.id}
          reminder={editor === "new" ? undefined : editor}
          timeZone={timeZone}
          defaultDay={from || todayInZone(timeZone)}
          onClose={() => setEditor(null)}
          onSaved={handleSaved}
        />
      )}
    </section>
  );
}
