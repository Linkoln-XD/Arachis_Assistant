import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { api, apiBase, apiOrigin } from "../api";
import { useLog, useSession } from "../session";

export function Layout() {
  const session = useSession();
  const log = useLog();
  const [online, setOnline] = useState<boolean | null>(null);
  const failed = log.filter((entry) => entry.status === 0 || entry.status >= 400).length;

  useEffect(() => {
    let cancelled = false;
    api.health().then(
      () => {
        if (!cancelled) setOnline(true);
      },
      () => {
        if (!cancelled) setOnline(false);
      },
    );
    void api.me().catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          <div>
            <p className="brand-name">Арахис</p>
            <p className="brand-note">проверка API</p>
          </div>
        </div>
        <nav className="nav">
          <NavLink to="/" end className={navClass}>
            День
          </NavLink>
          <NavLink to="/tasks" className={navClass}>
            Задачи
          </NavLink>
          <NavLink to="/meetings" className={navClass}>
            Встречи
          </NavLink>
          <NavLink to="/reminders" className={navClass}>
            Напоминания
          </NavLink>
          <NavLink to="/profile" className={navClass}>
            Профиль
          </NavLink>
          <NavLink to="/log" className={navClass}>
            Журнал
            {failed > 0 && <span className="badge">{failed}</span>}
          </NavLink>
          <a className="nav-link" href={`${apiOrigin()}/docs`} target="_blank" rel="noreferrer">
            Swagger
          </a>
        </nav>
        <div className="sidebar-foot">
          <p className="who">{session?.user.email}</p>
          <p className="brand-note">{session?.user.timezone}</p>
          <p className={online ? "status ok" : "status"}>
            {online === null ? "Проверяю API…" : online ? "API отвечает" : "API недоступен"}
          </p>
          <p className="brand-note api-base">{apiBase()}</p>
          <button type="button" className="text-button light" onClick={() => void api.logout()}>
            Выйти
          </button>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}

function navClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "nav-link active" : "nav-link";
}
