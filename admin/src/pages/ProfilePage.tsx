import { useState, type FormEvent } from "react";
import { api, asApiError, type ApiError } from "../api";
import { Banner, PageHeader } from "../components/ui";
import { useSession } from "../session";
import { TIMEZONES, formatDateTime } from "../time";

export function ProfilePage() {
  const session = useSession();
  const user = session?.user;
  const [zone, setZone] = useState(user?.timezone ?? "Europe/Moscow");
  const [custom, setCustom] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  if (!session || !user) return null;

  const options = TIMEZONES.includes(user.timezone) ? TIMEZONES : [user.timezone, ...TIMEZONES];

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await api.patchTimezone(custom.trim() || zone);
      setZone(updated.timezone);
      setCustom("");
      setNotice(`Пояс теперь ${updated.timezone}. Моменты в базе те же, в ответах они показаны заново.`);
    } catch (caught) {
      setError(asApiError(caught));
    } finally {
      setPending(false);
    }
  }

  return (
    <section>
      <PageHeader
        title="Профиль"
        hint="Смена пояса не переписывает сохранённые моменты. created_at в ответе приходит уже в новом поясе — смещение видно в сырой строке."
      />
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      <Banner error={error} />
      <div className="profile-grid">
        <dl className="facts">
          <div>
            <dt>Почта</dt>
            <dd>{user.email}</dd>
          </div>
          <div>
            <dt>Идентификатор</dt>
            <dd>
              <code>{user.id}</code>
            </dd>
          </div>
          <div>
            <dt>Создан</dt>
            <dd>
              {formatDateTime(user.created_at, user.timezone)}
              <code className="block-code">{user.created_at}</code>
            </dd>
          </div>
          <div>
            <dt>Ключ доступа</dt>
            <dd>
              обновится сам около{" "}
              {new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" }).format(
                new Date(session.accessExpiresAt),
              )}
            </dd>
          </div>
        </dl>
        <form className="form card" onSubmit={(event) => void submit(event)}>
          <label className="field">
            <span>Часовой пояс</span>
            <select value={options.includes(zone) ? zone : user.timezone} onChange={(event) => setZone(event.target.value)}>
              {options.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Или свой пояс IANA</span>
            <input
              value={custom}
              onChange={(event) => setCustom(event.target.value)}
              placeholder="Неизвестный пояс даст invalid_timezone"
              spellCheck={false}
            />
          </label>
          <button type="submit" className="button" disabled={pending}>
            {pending ? "Сохраняю…" : "Сохранить пояс"}
          </button>
        </form>
      </div>
    </section>
  );
}
