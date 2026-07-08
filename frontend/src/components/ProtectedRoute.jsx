// frontend/src/components/ProtectedRoute.jsx
// ─────────────────────────────────────────────────────────
// Route guard — redirects to /login if user is not logged in.
//
// Used in App.jsx like this:
//   <Route path="/chat" element={
//     <ProtectedRoute>
//       <Chat />
//     </ProtectedRoute>
//   } />
//
// If not logged in → redirects to /login
// If logged in     → renders the wrapped component normally
// ─────────────────────────────────────────────────────────

import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ children }) {
  const { isLoggedIn, loading } = useAuth()

  // Still checking localStorage — show nothing to prevent flash
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

  // Not logged in — send to login page
  // replace={true} means the login page replaces this in browser history
  // so pressing back doesn't return to the protected page
  if (!isLoggedIn) {
    return <Navigate to="/login" replace />
  }

  // Logged in — render the actual page
  return children
}