export const TIMEZONES = [
  "Europe/Kaliningrad",
  "Europe/Moscow",
  "Europe/Samara",
  "Asia/Yekaterinburg",
  "Asia/Omsk",
  "Asia/Krasnoyarsk",
  "Asia/Irkutsk",
  "Asia/Yakutsk",
  "Asia/Vladivostok",
  "Asia/Magadan",
  "Asia/Kamchatka",
  "UTC",
  "Pacific/Auckland",
];

type WallParts = {
  year: string;
  month: string;
  day: string;
  hour: string;
  minute: string;
  second: string;
};

function partsInZone(date: Date, timeZone: string): WallParts {
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  const bag: Record<string, string> = {};
  for (const part of formatter.formatToParts(date)) {
    if (part.type !== "literal") bag[part.type] = part.value;
  }
  if (bag.hour === "24") {
    bag.hour = "00";
    const next = new Date(Date.UTC(Number(bag.year), Number(bag.month) - 1, Number(bag.day) + 1));
    bag.year = String(next.getUTCFullYear());
    bag.month = String(next.getUTCMonth() + 1).padStart(2, "0");
    bag.day = String(next.getUTCDate()).padStart(2, "0");
  }
  return bag as WallParts;
}

export function offsetMinutes(date: Date, timeZone: string): number {
  const parts = partsInZone(date, timeZone);
  const asUtc = Date.UTC(
    Number(parts.year),
    Number(parts.month) - 1,
    Number(parts.day),
    Number(parts.hour),
    Number(parts.minute),
    Number(parts.second),
  );
  return Math.round((asUtc - date.getTime()) / 60_000);
}

export function todayInZone(timeZone: string): string {
  const parts = partsInZone(new Date(), timeZone);
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function shiftIsoDate(iso: string, days: number): string {
  const [year, month, day] = iso.split("-").map(Number);
  const next = new Date(Date.UTC(year, month - 1, day + days));
  return next.toISOString().slice(0, 10);
}

export function wallTimeToIso(date: string, time: string, timeZone: string): string {
  const [year, month, day] = date.split("-").map(Number);
  const [hour, minute] = time.split(":").map(Number);
  const wallAsUtc = Date.UTC(year, month - 1, day, hour, minute, 0);
  const firstOffset = offsetMinutes(new Date(wallAsUtc), timeZone);
  const utc = wallAsUtc - firstOffset * 60_000;
  const offset = offsetMinutes(new Date(utc), timeZone);
  const sign = offset >= 0 ? "+" : "-";
  const abs = Math.abs(offset);
  const hours = String(Math.floor(abs / 60)).padStart(2, "0");
  const minutes = String(abs % 60).padStart(2, "0");
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date}T${pad(hour)}:${pad(minute)}:00${sign}${hours}:${minutes}`;
}

export function isoToWall(iso: string, timeZone: string): { date: string; time: string } {
  const parts = partsInZone(new Date(iso), timeZone);
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    time: `${parts.hour}:${parts.minute}`,
  };
}

export function futureWall(timeZone: string, hoursAhead: number): { date: string; time: string } {
  const parts = partsInZone(new Date(Date.now() + hoursAhead * 3_600_000), timeZone);
  return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}` };
}

export function defaultStart(day: string, timeZone: string): { date: string; time: string } {
  const today = todayInZone(timeZone);
  if (day !== today) return { date: day, time: "10:00" };
  const later = futureWall(timeZone, 1);
  if (later.date === today) return later;
  const evening = wallTimeToIso(today, "23:30", timeZone);
  if (new Date(evening).getTime() > Date.now() + 60_000) return { date: today, time: "23:30" };
  return later;
}

export function formatDay(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month - 1, day)));
}

export function formatLongDay(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Intl.DateTimeFormat("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month - 1, day)));
}

export function formatTime(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

export function formatDateTime(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone,
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

export function formatInterval(startIso: string, endIso: string, timeZone: string): string {
  const start = isoToWall(startIso, timeZone);
  const end = isoToWall(endIso, timeZone);
  if (start.date === end.date) return `${formatDateTime(startIso, timeZone)} – ${formatTime(endIso, timeZone)}`;
  return `${formatDateTime(startIso, timeZone)} – ${formatDateTime(endIso, timeZone)}`;
}
