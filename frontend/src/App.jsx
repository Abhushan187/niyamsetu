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
import Layout from './components/Layout'

// Pages
import Login   from './pages/Login'
import Chat    from './pages/Chat'
import Upload   from './pages/Upload'
import Users    from './pages/Users'
import Summaries from './pages/Summaries'
import Analytics from './pages/Analytics'
import KnowledgeBase from './pages/KnowledgeBase'

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
            <ProtectedRoute><Layout><Chat /></Layout></ProtectedRoute>
          } />

          <Route path="/summaries" element={
            <ProtectedRoute><Layout><Summaries /></Layout></ProtectedRoute>
          } />

          {/* ── Admin routes ───────────────────────────── */}
          <Route path="/admin/upload" element={
            <AdminRoute><Layout><Upload /></Layout></AdminRoute>
          } />

          <Route path="/admin/knowledge" element={
            <AdminRoute><Layout><KnowledgeBase /></Layout></AdminRoute>
          } />

          <Route path="/admin/analytics" element={
            <AdminRoute><Layout><Analytics /></Layout></AdminRoute>
          } />

          <Route path="/admin/users" element={
            <AdminRoute><Layout><Users /></Layout></AdminRoute>
          } />

          {/* Catch-all — unknown URLs redirect to login */}
          <Route path="*" element={<Navigate to="/login" replace />} />

        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}