import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ThemeProvider, ModeProvider } from '@/context'
import { AppLayout } from '@/components/layout/AppLayout'

// User Views
import { ChatView } from '@/views/user/ChatView'
import { TasksView } from '@/views/user/TasksView'
import { BrowserView } from '@/views/user/BrowserView'
import { DocumentsView } from '@/views/user/DocumentsView'
import { MemoryView } from '@/views/user/MemoryView'
import { SettingsView } from '@/views/user/SettingsView'

// Developer Views
import { AppInfoView } from '@/views/dev/AppInfoView'
import { RuntimeStatusView } from '@/views/dev/RuntimeStatusView'
import { ConnectivityView } from '@/views/dev/ConnectivityView'
import { DiagnosticsView } from '@/views/dev/DiagnosticsView'
import { LogsView } from '@/views/dev/LogsView'
import { TelemetryView } from '@/views/dev/TelemetryView'
import { VerificationView } from '@/views/dev/VerificationView'

export function App() {
  return (
    <ThemeProvider>
      <ModeProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              {/* Default Redirect */}
              <Route path="/" element={<Navigate to="/chat" replace />} />

              {/* User Mode Views */}
              <Route path="/chat" element={<ChatView />} />
              <Route path="/tasks" element={<TasksView />} />
              <Route path="/browser" element={<BrowserView />} />
              <Route path="/documents" element={<DocumentsView />} />
              <Route path="/memory" element={<MemoryView />} />
              <Route path="/settings" element={<SettingsView />} />

              {/* Developer Mode Views */}
              <Route path="/dev/info" element={<AppInfoView />} />
              <Route path="/dev/runtime" element={<RuntimeStatusView />} />
              <Route path="/dev/connectivity" element={<ConnectivityView />} />
              <Route path="/dev/diagnostics" element={<DiagnosticsView />} />
              <Route path="/dev/logs" element={<LogsView />} />
              <Route path="/dev/telemetry" element={<TelemetryView />} />
              <Route path="/dev/verification" element={<VerificationView />} />

              {/* Catch-all */}
              <Route path="*" element={<Navigate to="/chat" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ModeProvider>
    </ThemeProvider>
  )
}

export default App
