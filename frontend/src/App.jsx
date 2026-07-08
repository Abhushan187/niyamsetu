// frontend/src/App.jsx
// ─────────────────────────────────────────────────────────
// Root component — sets up routing and auth context.
//
// Route structure:
//   /              → redirects to /login
//   /login         → Login page (public)
//   /chat          → Chat page (requires login)
//   /search        → Search page (requires login)
//   /graph         → GR Graph page (requires login)
//   /history       → My query history (requires login)
//   /admin/upload  → Upload GRs (admin only)
//   /admin/embed   → Build vector store (admin only)
//   /admin/summary → Generate summaries (admin only)
//   /admin/logs    → All query logs (admin only)
//   /admin/users   → User management (admin only)
// ─────────────────────────────────────────────────────────

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import AdminRoute from './components/AdminRoute'

// Pages
import Login   from './pages/Login'
import Chat    from './pages/Chat'
import Search  from './pages/Search'
import Graph   from './pages/Graph'
import History from './pages/History'
import Upload  from './pages/Upload'
import Embed   from './pages/Embed'
import Summary from './pages/Summary'
import Logs    from './pages/Logs'
import Users   from './pages/Users'

export default function App() {
  return (
    // BrowserRouter enables URL-based navigation
    <BrowserRouter>
      {/* AuthProvider wraps everything so all pages can useAuth() */}
      <AuthProvider>
        <Routes>

          {/* ── Public routes ─────────────────────────── */}
          {/* Root → redirect to login */}
          <Route path="/" element={<Navigate to="/login" replace />} />

          {/* Login page — only page accessible without token */}
          <Route path="/login" element={<Login />} />

          {/* ── User routes (login required) ──────────── */}
          <Route path="/chat" element={
            <ProtectedRoute><Chat /></ProtectedRoute>
          } />

          <Route path="/search" element={
            <ProtectedRoute><Search /></ProtectedRoute>
          } />

          <Route path="/graph" element={
            <ProtectedRoute><Graph /></ProtectedRoute>
          } />

          <Route path="/history" element={
            <ProtectedRoute><History /></ProtectedRoute>
          } />

          {/* ── Admin routes (admin role required) ────── */}
          <Route path="/admin/upload" element={
            <AdminRoute><Upload /></AdminRoute>
          } />

          <Route path="/admin/embed" element={
            <AdminRoute><Embed /></AdminRoute>
          } />

          <Route path="/admin/summary" element={
            <AdminRoute><Summary /></AdminRoute>
          } />

          <Route path="/admin/logs" element={
            <AdminRoute><Logs /></AdminRoute>
          } />

          <Route path="/admin/users" element={
            <AdminRoute><Users /></AdminRoute>
          } />

          {/* Catch-all — unknown URLs redirect to login */}
          <Route path="*" element={<Navigate to="/login" replace />} />

        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}