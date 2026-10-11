from datetime import UTC, datetime, timedelta


class LoginRateLimiter:
    def __init__(self, limit: int = 10, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window = timedelta(seconds=window_seconds)
        self._attempts: dict[str, list[datetime]] = {}

    def reset(self) -> None:
        self._attempts.clear()

    def allow(self, key: str) -> bool:
        now = datetime.now(UTC)
        recent = [moment for moment in self._attempts.get(key, []) if now - moment < self.window]
        if len(recent) >= self.limit:
            self._attempts[key] = recent
            return False
        recent.append(now)
        self._attempts[key] = recent
        return True
