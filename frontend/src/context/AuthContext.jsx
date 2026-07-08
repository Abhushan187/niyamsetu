// frontend/src/context/AuthContext.jsx
// ─────────────────────────────────────────────────────────
// Global auth state — who is logged in, their role, token.
//
// How React Context works:
//   AuthProvider wraps the entire app in App.jsx.
//   Any component inside can call useAuth() to get:
//     - user: { username, name, role } or null if not logged in
//     - login(username, password): logs in, stores token
//     - logout(): clears everything, redirects to /login
//     - isAdmin: true if role === 'admin'
//     - loading: true while checking if user is already logged in
// ─────────────────────────────────────────────────────────

import { createContext, useContext, useState, useEffect } from 'react'
import client from '../api/client'

// Create the context object
// Components import useAuth() to read from this
const AuthContext = createContext(null)


export function AuthProvider({ children }) {
  // user = null means not logged in
  // user = { username, name, role } means logged in
  const [user, setUser]       = useState(null)

  // loading = true while we check localStorage on first page load
  // Prevents flash of login page when user is already logged in
  const [loading, setLoading] = useState(true)


  // ── On app load — restore session from localStorage ────
  // If user previously logged in and token is still valid,
  // restore their session without making them login again.
  useEffect(() => {
    const restoreSession = async () => {
      const token    = localStorage.getItem('niyamsetu_token')
      const savedUser = localStorage.getItem('niyamsetu_user')

      if (token && savedUser) {
        try {
          // Verify token is still valid by calling /api/auth/me
          // If token expired, this throws 401 → interceptor clears storage
          await client.get('/auth/me')

          // Token valid — restore user from storage
          setUser(JSON.parse(savedUser))
        } catch {
          // Token invalid — clear storage, stay on login
          localStorage.removeItem('niyamsetu_token')
          localStorage.removeItem('niyamsetu_user')
        }
      }

      // Done checking — allow app to render
      setLoading(false)
    }

    restoreSession()
  }, [])


  // ── Login function ────────────────────────────────────
  const login = async (username, password) => {
    // Call POST /api/auth/login
    const response = await client.post('/auth/login', {
      username,
      password,
    })

    const { access_token, username: uname, name, role } = response.data

    // Store token — client.js interceptor picks this up automatically
    localStorage.setItem('niyamsetu_token', access_token)

    // Store user info so we can restore session on page refresh
    const userData = { username: uname, name, role }
    localStorage.setItem('niyamsetu_user', JSON.stringify(userData))

    // Update state — triggers re-render across all components
    setUser(userData)

    return userData
  }


  // ── Logout function ───────────────────────────────────
  const logout = async () => {
    try {
      // Tell backend about logout (optional — for logging)
      await client.post('/auth/logout')
    } catch {
      // Even if this fails, we still clear local state
    }

    // Clear everything
    localStorage.removeItem('niyamsetu_token')
    localStorage.removeItem('niyamsetu_user')
    setUser(null)
  }


  // Values available to all components via useAuth()
  const value = {
    user,
    login,
    logout,
    loading,
    isAdmin: user?.role === 'admin',
    isLoggedIn: !!user,
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}


// ── Custom hook ───────────────────────────────────────────
// Components call useAuth() instead of useContext(AuthContext)
// Cleaner and throws helpful error if used outside AuthProvider
export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider')
  }
  return context
}