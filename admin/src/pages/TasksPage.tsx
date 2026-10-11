import { useEffect, useState } from "react";
import { api, asApiError, type ApiError } from "../api";
import { TaskEditor } from "../components/editors";
import { Banner, DateFields, PageHeader, Pager, RawJson } from "../components/ui";
import { STATUS } from "../labels";
import { useSession } from "../session";
import { formatDay } from "../time";
import type { Page, Task } from "../types";

const limit = 50;

export function TasksPage() {
  const session = useSession();
  const timeZone = session?.user.timezone ?? "Europe/Moscow";
  const [status, setStatus] = useState("all");
  const [due, setDue] = useState("any");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<Page<Task> | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [editor, setEditor] = useState<Task | "new" | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    setLoading(true);
    api
      .listTasks({ status, due, from, to, limit, offset })
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
  }, [session, status, due, from, to, offset, timeZone, version]);

  if (!session) return null;

  function refresh() {
    setVersion((value) => value + 1);
  }

  function handleSaved(message: string) {
    setEditor(null);
    setNotice(message);
    setOffset(0);
    refresh();
  }

  async function complete(task: Task) {
    setNotice(null);
    try {
      const result = await api.completeTask(task.id);
      setNotice(result.status_changed ? "Задача выполнена" : "Задача уже была выполнена");
      refresh();
    } catch (caught) {
      setError(asApiError(caught));
    }
  }

  async function reopen(task: Task) {
    setNotice(null);
    try {
      const result = await api.reopenTask(task.id);
      setNotice(result.status_changed ? "Задача снова активна" : "Задача уже была активна");
      refresh();
    } catch (caught) {
      setError(asApiError(caught));
    }
  }

  async function remove(task: Task) {
    if (!window.confirm(`Удалить «${task.description}»?`)) return;
    setNotice(null);
    try {
      await api.deleteTask(task.id, crypto.randomUUID());
      setNotice("Задача удалена");
      refresh();
    } catch (caught) {
      setError(asApiError(caught));
    }
  }

  return (
    <section>
      <PageHeader
        title="Задачи"
        hint="Список всех задач, в том числе без срока. Пара from и to фильтрует по дате срока. Один край без другого отвечает required, а «без срока» вместе с датами — invalid_range."
        action={
          <button type="button" className="button" onClick={() => setEditor("new")}>
            Новая задача
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
            <option value="active">активные</option>
            <option value="completed">выполненные</option>
          </select>
        </label>
        <label className="field inline">
          <span>Срок</span>
          <select
            value={due}
            onChange={(event) => {
              setDue(event.target.value);
              setOffset(0);
            }}
          >
            <option value="any">любой</option>
            <option value="dated">со сроком</option>
            <option value="undated">без срока</option>
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
              <th>Описание</th>
              <th>Срок</th>
              <th>Статус</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {page?.items.map((task) => (
              <tr key={task.id} className={task.status === "completed" ? "done" : undefined}>
                <td>
                  <p className="item-title">{task.description}</p>
                  <RawJson value={task} />
                </td>
                <td>{task.due_on ? formatDay(task.due_on) : "без срока"}</td>
                <td>{STATUS[task.status]}</td>
                <td>
                  <div className="row-actions">
                    <button type="button" className="text-button" onClick={() => setEditor(task)}>
                      Изменить
                    </button>
                    {task.status === "active" ? (
                      <button type="button" className="text-button" onClick={() => void complete(task)}>
                        Выполнить
                      </button>
                    ) : (
                      <button type="button" className="text-button" onClick={() => void reopen(task)}>
                        Вернуть
                      </button>
                    )}
                    <button type="button" className="text-button danger" onClick={() => void remove(task)}>
                      Удалить
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {page && page.items.length === 0 && !error && <p className="empty">Задач нет.</p>}
      {page && <Pager offset={page.offset} limit={page.limit} total={page.total} onOffset={setOffset} />}
      {editor && (
        <TaskEditor
          key={editor === "new" ? "new" : editor.id}
          task={editor === "new" ? undefined : editor}
          onClose={() => setEditor(null)}
          onSaved={handleSaved}
        />
      )}
    </section>
  );
}
