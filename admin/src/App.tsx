import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AuthPage } from "./pages/AuthPage";
import { CalendarPage } from "./pages/CalendarPage";
import { LogPage } from "./pages/LogPage";
import { MeetingsPage } from "./pages/MeetingsPage";
import { ProfilePage } from "./pages/ProfilePage";
import { RemindersPage } from "./pages/RemindersPage";
import { TasksPage } from "./pages/TasksPage";
import { RequireAuth } from "./session";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<AuthPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<Layout />}>
            <Route index element={<CalendarPage />} />
            <Route path="tasks" element={<TasksPage />} />
            <Route path="meetings" element={<MeetingsPage />} />
            <Route path="reminders" element={<RemindersPage />} />
            <Route path="profile" element={<ProfilePage />} />
            <Route path="log" element={<LogPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
