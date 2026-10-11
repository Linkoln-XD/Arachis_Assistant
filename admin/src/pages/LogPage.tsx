import { clearLog } from "../api";
import { PageHeader } from "../components/ui";
import { useLog } from "../session";

export function LogPage() {
  const entries = useLog();

  return (
    <section>
      <PageHeader
        title="Журнал"
        hint="Последние запросы этой вкладки. Пароли и токены скрыты. Журнал очищается при перезагрузке страницы."
        action={
          <button type="button" className="button ghost" onClick={() => clearLog()} disabled={entries.length === 0}>
            Очистить
          </button>
        }
      />
      {entries.length === 0 && <p className="empty">Запросов пока не было.</p>}
      <div className="log">
        {entries.map((entry) => (
          <details key={entry.id} className={entry.status === 0 || entry.status >= 400 ? "log-entry bad" : "log-entry"}>
            <summary>
              <time>
                {new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(
                  new Date(entry.at),
                )}
              </time>
              <span className={`method ${entry.method.toLowerCase()}`}>{entry.method}</span>
              <span className="log-path">{entry.path}</span>
              <span className="log-status">{entry.status || "сеть"}</span>
              <span className="log-ms">{entry.ms} мс</span>
            </summary>
            {entry.location && (
              <p>
                Location <code>{entry.location}</code>
              </p>
            )}
            <div className="log-bodies">
              <div>
                <p className="hint">Запрос</p>
                <pre>{JSON.stringify(entry.requestBody, null, 2)}</pre>
              </div>
              <div>
                <p className="hint">Ответ</p>
                <pre>{JSON.stringify(entry.responseBody, null, 2)}</pre>
              </div>
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}
