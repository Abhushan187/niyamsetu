// frontend/src/context/AdminContext.jsx
// Shared admin state — pending summary count + batch job progress.
// Sidebar reads this to show a live badge from ANY page.
// KnowledgeBase reads/writes this to trigger and display the batch job.

import { createContext, useContext, useState, useEffect, useRef } from 'react'
import client from '../api/client'
import { useAuth } from './AuthContext'

const AdminContext = createContext(null)

export function AdminProvider({ children }) {
  const { isAdmin } = useAuth()

  const [pendingCount, setPendingCount] = useState(0)
  const [batchState,   setBatchState]   = useState(null)

  const pendingPollRef = useRef(null)
  const batchPollRef   = useRef(null)
  const batchRunningRef = useRef(false) // avoids stale-closure issue inside setInterval

  useEffect(() => {
    batchRunningRef.current = !!batchState?.running
  }, [batchState])

  useEffect(() => {
    if (!isAdmin) {
      setPendingCount(0)
      setBatchState(null)
      return
    }
    loadPending()
    checkBatchStatus()
    startPendingPolling()
    return () => { stopPendingPolling(); stopBatchPolling() }
  }, [isAdmin])

  const loadPending = async () => {
    try {
      const res = await client.get('/summary/pending')
      setPendingCount(res.data.total ?? (res.data.pending || []).length)
    } catch { /* silent — badge just won't show */ }
  }

  const startPendingPolling = () => {
    if (pendingPollRef.current) return
    pendingPollRef.current = setInterval(() => {
      // Skip while a batch job is running — batch polling already keeps count fresh then
      if (!batchRunningRef.current) loadPending()
    }, 15000)
  }

  const stopPendingPolling = () => {
    if (pendingPollRef.current) { clearInterval(pendingPollRef.current); pendingPollRef.current = null }
  }

  const checkBatchStatus = async () => {
    try {
      const res = await client.get('/summary/batch-status')
      setBatchState(res.data.state)
      if (res.data.state?.running) startBatchPolling()
    } catch { /* silent */ }
  }

  const startBatchPolling = () => {
    if (batchPollRef.current) return
    batchPollRef.current = setInterval(async () => {
      try {
        const res = await client.get('/summary/batch-status')
        setBatchState(res.data.state)
        if (!res.data.state?.running) {
          stopBatchPolling()
          loadPending() // refresh true count once job finishes
        }
      } catch { /* silent */ }
    }, 3000)
  }

  const stopBatchPolling = () => {
    if (batchPollRef.current) { clearInterval(batchPollRef.current); batchPollRef.current = null }
  }

  const startBatchSummarize = async () => {
    try {
      const res = await client.post('/summary/generate-batch')
      if (res.data.success) {
        setBatchState(res.data.state)
        startBatchPolling()
      }
      return res.data
    } catch (err) {
      return { success: false, message: err.response?.data?.detail || 'Could not start summarization.' }
    }
  }

  return (
    <AdminContext.Provider value={{
      pendingCount, batchState, startBatchSummarize, refreshPending: loadPending,
    }}>
      {children}
    </AdminContext.Provider>
  )
}

export function useAdmin() {
  return useContext(AdminContext)
}