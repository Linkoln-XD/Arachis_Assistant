import { useEffect, useState } from "react";
import { api, asApiError, type ApiError } from "../api";
import { MeetingEditor } from "../components/editors";
import { Banner, DateFields, PageHeader, Pager, RawJson } from "../components/ui";
import { useSession } from "../session";
import { formatInterval, todayInZone } from "../time";
import type { Meeting, Page } from "../types";

const limit = 50;

export function MeetingsPage() {
  const session = useSession();
  const timeZone = session?.user.timezone ?? "Europe/Moscow";
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<Page<Meeting> | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [editor, setEditor] = useState<Meeting | "new" | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    setLoading(true);
    api
      .listMeetings({ from, to, limit, offset })
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
  }, [session, from, to, offset, timeZone, version]);

  if (!session) return null;

  function handleSaved(message: string) {
    setEditor(null);
    setNotice(message);
    setOffset(0);
    setVersion((value) => value + 1);
  }

  async function remove(meeting: Meeting) {
    if (!window.confirm(`Удалить «${meeting.title}»?`)) return;
    setNotice(null);
    try {
      await api.deleteMeeting(meeting.id, crypto.randomUUID());
      setNotice("Встреча удалена");
      setVersion((value) => value + 1);
    } catch (caught) {
      setError(asApiError(caught));
    }
  }

  return (
    <section>
      <PageHeader
        title="Встречи"
        hint="Пустые даты показывают все встречи. Если заполнен только один край периода, сервер отвечает required."
        action={
          <button type="button" className="button" onClick={() => setEditor("new")}>
            Новая встреча
          </button>
        }
      />
      <div className="toolbar">
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
              <th>Название</th>
              <th>Интервал</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {page?.items.map((meeting) => (
              <tr key={meeting.id}>
                <td>
                  <p className="item-title">{meeting.title}</p>
                  <RawJson value={meeting} />
                </td>
                <td>{formatInterval(meeting.starts_at, meeting.ends_at, timeZone)}</td>
                <td>
                  <div className="row-actions">
                    <button type="button" className="text-button" onClick={() => setEditor(meeting)}>
                      Изменить
                    </button>
                    <button type="button" className="text-button danger" onClick={() => void remove(meeting)}>
                      Удалить
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {page && page.items.length === 0 && !error && <p className="empty">Встреч нет.</p>}
      {page && <Pager offset={page.offset} limit={page.limit} total={page.total} onOffset={setOffset} />}
      {editor && (
        <MeetingEditor
          key={editor === "new" ? "new" : editor.id}
          meeting={editor === "new" ? undefined : editor}
          timeZone={timeZone}
          defaultDay={from || todayInZone(timeZone)}
          onClose={() => setEditor(null)}
          onSaved={handleSaved}
        />
      )}
    </section>
  );
}
