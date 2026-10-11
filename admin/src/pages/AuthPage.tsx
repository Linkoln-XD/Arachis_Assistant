import { useEffect, useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { api, asApiError, type ApiError } from "../api";
import { useSession } from "../session";
import { TIMEZONES } from "../time";
import { Banner } from "../components/ui";

export function AuthPage() {
  const session = useSession();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [zone, setZone] = useState("Europe/Moscow");
  const [customZone, setCustomZone] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    document.title = "Вход · Арахис";
  }, []);

  if (session) return <Navigate to="/" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      if (mode === "login") await api.login(email, password);
      else await api.register(email, password, customZone.trim() || zone);
    } catch (caught) {
      setError(asApiError(caught));
      setPending(false);
    }
  }

  return (
    <div className="auth-screen">
      <section className="auth-card">
        <div className="brand auth-brand">
          <span className="mark" aria-hidden="true" />
          <div>
            <p className="brand-name dark">Арахис</p>
            <p className="brand-note dark">админка для проверки календаря</p>
          </div>
        </div>
        <p className="lede">
          Вход обычным пользователем. Отдельной роли нет: страница вызывает то же API, что и будущее приложение.
        </p>
        <div className="tabs">
          <button type="button" className={mode === "login" ? "tab active" : "tab"} onClick={() => switchMode("login")}>
            Вход
          </button>
          <button
            type="button"
            className={mode === "register" ? "tab active" : "tab"}
            onClick={() => switchMode("register")}
          >
            Регистрация
          </button>
        </div>
        <Banner error={error} />
        <form className="form" onSubmit={(event) => void submit(event)}>
          <label className="field">
            <span>Почта</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="username"
              autoFocus
            />
          </label>
          <p className="hint">Пробелы по краям убираются, регистр не важен.</p>
          <label className="field">
            <span>Пароль</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </label>
          {mode === "register" && (
            <>
              <p className="hint">От 8 символов. Пробелы по краям пароля сохраняются.</p>
              <label className="field">
                <span>Часовой пояс</span>
                <select value={zone} onChange={(event) => setZone(event.target.value)}>
                  {TIMEZONES.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Или свой пояс IANA</span>
                <input
                  value={customZone}
                  onChange={(event) => setCustomZone(event.target.value)}
                  placeholder="Неизвестный пояс даст invalid_timezone"
                  spellCheck={false}
                />
              </label>
            </>
          )}
          <button type="submit" className="button" disabled={pending}>
            {pending ? "Секунду…" : mode === "login" ? "Войти" : "Создать аккаунт"}
          </button>
        </form>
      </section>
    </div>
  );

  function switchMode(next: "login" | "register") {
    setMode(next);
    setError(null);
  }
}
