import { useState } from "react";
import { ApiError, api, asApiError } from "../api";
import type { Meeting, MeetingWrite, Reminder, ReminderWrite, Task, TaskWrite } from "../types";
import { Banner, Modal, OverlapDialog } from "./ui";
import { MeetingForm, ReminderForm, TaskForm } from "./forms";

function savedWithOverlaps(count: number): string {
  if (count === 0) return "Встреча сохранена";
  if (count === 1) return "Встреча сохранена параллельно с одной другой";
  return `Встреча сохранена параллельно с ${count} другими`;
}

export function TaskEditor({
  task,
  defaultDue,
  onClose,
  onSaved,
}: {
  task?: Task;
  defaultDue?: string;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(body: TaskWrite, idempotencyKey?: string) {
    setPending(true);
    setError(null);
    try {
      if (task) {
        await api.updateTask(task.id, body);
        onSaved("Задача сохранена");
      } else {
        const key = idempotencyKey ?? crypto.randomUUID();
        await api.createTask(body, key);
        onSaved(`Задача создана. Ключ ${key}`);
      }
    } catch (caught) {
      setError(asApiError(caught));
      setPending(false);
    }
  }

  return (
    <Modal title={task ? "Задача" : "Новая задача"} onClose={() => { if (!pending) onClose(); }}>
      <Banner error={error} />
      <TaskForm task={task} defaultDue={defaultDue} pending={pending} onSubmit={submit} onCancel={onClose} />
    </Modal>
  );
}

export function MeetingEditor({
  meeting,
  timeZone,
  defaultDay,
  onClose,
  onSaved,
}: {
  meeting?: Meeting;
  timeZone: string;
  defaultDay: string;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState(false);
  const [overlap, setOverlap] = useState<{ error: ApiError; body: MeetingWrite } | null>(null);

  async function submit(body: MeetingWrite, idempotencyKey?: string) {
    setPending(true);
    setError(null);
    try {
      if (meeting) {
        const saved = await api.updateMeeting(meeting.id, body);
        onSaved(savedWithOverlaps(saved.overlaps.length));
      } else {
        const key = idempotencyKey ?? crypto.randomUUID();
        const saved = await api.createMeeting(body, key);
        const base = savedWithOverlaps(saved.overlaps.length);
        onSaved(saved.overlaps.length > 0 ? base : `Встреча создана. Ключ ${key}`);
      }
    } catch (caught) {
      const apiError = asApiError(caught);
      if (apiError.code === "overlap") setOverlap({ error: apiError, body });
      else setError(apiError);
      setPending(false);
    }
  }

  async function confirmOverlap() {
    if (!overlap) return;
    setPending(true);
    setError(null);
    const body = { ...overlap.body, allow_overlap: true };
    try {
      if (meeting) {
        const saved = await api.updateMeeting(meeting.id, body);
        onSaved(savedWithOverlaps(saved.overlaps.length));
      } else {
        const saved = await api.createMeeting(body, crypto.randomUUID());
        onSaved(savedWithOverlaps(saved.overlaps.length));
      }
    } catch (caught) {
      setOverlap(null);
      setError(asApiError(caught));
      setPending(false);
    }
  }

  return (
    <>
      <Modal
        title={meeting ? "Встреча" : "Новая встреча"}
        onClose={() => {
          if (!pending && !overlap) onClose();
        }}
      >
        <Banner error={error} />
        <MeetingForm
          meeting={meeting}
          timeZone={timeZone}
          defaultDay={defaultDay}
          pending={pending}
          onSubmit={submit}
          onCancel={onClose}
        />
      </Modal>
      {overlap && (
        <OverlapDialog
          message={overlap.error.message}
          conflicts={overlap.error.conflicts()}
          timeZone={timeZone}
          pending={pending}
          onCancel={() => setOverlap(null)}
          onConfirm={() => void confirmOverlap()}
        />
      )}
    </>
  );
}

export function ReminderEditor({
  reminder,
  timeZone,
  defaultDay,
  onClose,
  onSaved,
}: {
  reminder?: Reminder;
  timeZone: string;
  defaultDay: string;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(body: ReminderWrite, idempotencyKey?: string) {
    setPending(true);
    setError(null);
    try {
      if (reminder) {
        await api.updateReminder(reminder.id, body);
        onSaved("Напоминание сохранено");
      } else {
        const key = idempotencyKey ?? crypto.randomUUID();
        await api.createReminder(body, key);
        onSaved(`Напоминание создано. Ключ ${key}`);
      }
    } catch (caught) {
      setError(asApiError(caught));
      setPending(false);
    }
  }

  return (
    <Modal title={reminder ? "Напоминание" : "Новое напоминание"} onClose={() => { if (!pending) onClose(); }}>
      <Banner error={error} />
      <ReminderForm
        reminder={reminder}
        timeZone={timeZone}
        defaultDay={defaultDay}
        pending={pending}
        onSubmit={submit}
        onCancel={onClose}
      />
    </Modal>
  );
}
