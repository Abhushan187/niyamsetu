// frontend/src/components/AdminRoute.jsx
// ─────────────────────────────────────────────────────────
// Route guard — redirects non-admins away from admin pages.
//
// Used in App.jsx like this:
//   <Route path="/admin/upload" element={
//     <AdminRoute>
//       <Upload />
//     </AdminRoute>
//   } />
//
// If not logged in  → redirects to /login
// If logged in but not admin → redirects to /chat
// If admin          → renders the wrapped component normally
// ─────────────────────────────────────────────────────────

import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function AdminRoute({ children }) {
  const { isLoggedIn, isAdmin, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center"
           style={{ background: '#0F1117' }}>
        <div style={{ color: '#FF6B00', fontSize: '1.1rem' }}>
          Loading...
        </div>
      </div>
    )
  }

  // Not logged in at all
  if (!isLoggedIn) {
    return <Navigate to="/login" replace />
  }

  // Logged in but not admin — redirect to chat
  if (!isAdmin) {
    return <Navigate to="/chat" replace />
  }

  // Admin — render the page
  return children
}