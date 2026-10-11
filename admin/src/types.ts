export type User = {
  id: string;
  email: string;
  timezone: string;
  created_at: string;
};

export type SessionResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token: string;
  refresh_expires_in: number;
  user: User;
};

export type Task = {
  id: string;
  type: "task";
  description: string;
  due_on: string | null;
  status: "active" | "completed";
  completed_at: string | null;
  source_id: string | null;
  created_at: string;
  updated_at: string;
};

export type Meeting = {
  id: string;
  type: "meeting";
  title: string;
  starts_at: string;
  ends_at: string;
  source_id: string | null;
  created_at: string;
  updated_at: string;
};

export type Reminder = {
  id: string;
  type: "reminder";
  text: string;
  fire_at: string;
  status: "pending" | "fired";
  fired_at: string | null;
  source_id: string | null;
  created_at: string;
  updated_at: string;
};

export type CalendarItem = Task | Meeting | Reminder;

export type Page<T> = {
  items: T[];
  limit: number;
  offset: number;
  total: number;
};

export type CalendarResponse = {
  from: string;
  to: string;
  timezone: string;
  items: CalendarItem[];
};

export type TaskWrite = {
  description?: string;
  due_on?: string | null;
};

export type MeetingWrite = {
  title?: string;
  starts_at?: string;
  ends_at?: string;
  allow_overlap?: boolean;
};

export type ReminderWrite = {
  text?: string;
  fire_at?: string;
};

export type TaskStatusChange = {
  task: Task;
  status_changed: boolean;
};

export type MeetingSaved = {
  meeting: Meeting;
  overlaps: Meeting[];
};
