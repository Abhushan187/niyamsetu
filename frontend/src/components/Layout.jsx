// frontend/src/components/Layout.jsx
// ─────────────────────────────────────────────────────────
// Shared layout — Navbar on top, Sidebar left, page content right.
// Every protected page is wrapped in this.
// ─────────────────────────────────────────────────────────

import { useState } from 'react'
import Navbar  from './Navbar'
import Sidebar from './Sidebar'
import { ChatProvider } from '../context/ChatContext'
import { AdminProvider } from '../context/AdminContext'

export default function Layout({ children }) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <AdminProvider>
    <ChatProvider>
    <div style={{
      height: '100vh',
      background: '#0F1117',
      fontFamily: 'Inter, sans-serif',
      overflow: 'hidden',
    }}>

      {/* Fixed top navbar */}
      <Navbar collapsed={collapsed} onToggleSidebar={() => setCollapsed(!collapsed)} />

      {/* Below navbar — sidebar + content */}
      <div style={{
        display: 'flex',
        height: 'calc(100vh - 56px)',
        marginTop: '56px',      // push below fixed navbar
      }}>

        {/* Left sidebar */}
        <Sidebar collapsed={collapsed} />

        {/* Main content — scrollable */}
        <div style={{
          flex: 1,
          overflowY: 'auto',
          background: '#0F1117',
        }}>
          {children}
        </div>

      </div>
    </div>
    </ChatProvider>
    </AdminProvider>
  )
}