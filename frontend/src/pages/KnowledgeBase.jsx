// frontend/src/pages/KnowledgeBase.jsx
// Admin-only control panel for the AI knowledge base.
// Embedding and summarization are two independent, explicit actions.
// Live pending/progress state lives in AdminContext so Sidebar can show it too.

import { useState, useEffect, useRef } from 'react'
import client from '../api/client'
import { useAdmin } from '../context/AdminContext'

export default function KnowledgeBase() {
  const [files,      setFiles]      = useState([])
  const [loading,    setLoading]    = useState(true)
  const [error,      setError]      = useState('')
  const [embedState, setEmbedState] = useState(null)
  const pollRef = useRef(null)

  const { pendingCount, batchState, startBatchSummarize } = useAdmin()

  useEffect(() => {
    loadFiles()
    checkStatus()
    return () => stopPolling()
  }, [])

  const loadFiles = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await client.get('/upload/list')
      setFiles(res.data.files || [])
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not load documents.')
    } finally {
      setLoading(false)
    }
  }

  const checkStatus = async () => {
    try {
      const res = await client.get('/embed/status')
      setEmbedState(res.data)
      if (res.data.state?.running) startPolling()
    } catch { /* silent */ }
  }

  const startPolling = () => {
    if (pollRef.current) return
    pollRef.current = setInterval(async () => {
      try {
        const res = await client.get('/embed/status')
        setEmbedState(res.data)
        if (!res.data.state?.running) {
          stopPolling()
          loadFiles()
        }
      } catch { /* silent */ }
    }, 3000)
  }

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }

  const startEmbedding = async () => {
    setError('')
    try {
      const res = await client.post('/embed/start')
      if (!res.data.success) {
        setError(res.data.message || 'Could not start embedding.')
        return
      }
      setEmbedState({ success: true, state: res.data.state, vector_ready: false })
      startPolling()
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not start embedding.')
    }
  }

  const handleSummarizeAll = async () => {
    setError('')
    const res = await startBatchSummarize()
    if (!res.success) setError(res.message || 'Could not start summarization.')
  }

  const notEmbeddedCount = files.filter(f => !f.embedded).length
  const state      = embedState?.state
  const isRunning  = state?.running

  const isBatchRunning = batchState?.running

  return (
    <div style={{
      minHeight: '100%', background: '#0F1117',
      padding: '28px 32px', fontFamily: 'Inter, sans-serif',
    }}>

      {/* Header */}
      <div style={{ marginBottom: '20px' }}>
        <h1 style={{ color: '#E8EAF0', fontSize: '1.4rem', margin: '0 0 4px', fontWeight: '700' }}>
          🗄️ Knowledge Base
        </h1>
        <p style={{ color: '#555', fontSize: '0.85rem', margin: 0 }}>
          Manage which GR documents are indexed and searchable by the AI.
        </p>
      </div>

      {error && (
        <div style={{
          background: '#2A0F0F', border: '1px solid #EF4444', borderRadius: '8px',
          padding: '12px 16px', color: '#EF4444', fontSize: '0.85rem', marginBottom: '20px',
        }}>
          ❌ {error}
        </div>
      )}

      {/* Actions panel */}
      <div style={{
        background: '#1A1D2E', border: '1px solid #2A2D3E', borderRadius: '14px',
        padding: '20px 22px', marginBottom: '24px',
      }}>
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px',
        }}>
          <div>
            <div style={{ color: '#E8EAF0', fontSize: '0.95rem', fontWeight: '600', marginBottom: '4px' }}>
              Vector Store & Summaries
            </div>
            <div style={{ color: '#555', fontSize: '0.8rem' }}>
              {notEmbeddedCount > 0
                ? `${notEmbeddedCount} document${notEmbeddedCount !== 1 ? 's' : ''} not yet embedded.`
                : 'All uploaded documents are embedded.'}
              {pendingCount > 0 && ` · ${pendingCount} awaiting summary.`}
            </div>
          </div>

          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <button
              onClick={startEmbedding}
              disabled={isRunning || notEmbeddedCount === 0}
              style={{
                background: isRunning || notEmbeddedCount === 0 ? '#3A1800' : '#FF6B00',
                color: 'white', border: 'none', borderRadius: '10px',
                padding: '11px 22px', fontSize: '0.88rem', fontWeight: '600',
                cursor: isRunning || notEmbeddedCount === 0 ? 'not-allowed' : 'pointer',
                fontFamily: 'Inter, sans-serif', whiteSpace: 'nowrap',
              }}
            >
              {isRunning ? '⏳ Embedding…' : '⚙️ Build Vector Store'}
            </button>

            <button
              onClick={handleSummarizeAll}
              disabled={isBatchRunning || pendingCount === 0}
              style={{
                background: isBatchRunning || pendingCount === 0 ? '#2A2410' : '#FACC15',
                color: isBatchRunning || pendingCount === 0 ? '#7A7250' : '#1A1D2E',
                border: 'none', borderRadius: '10px',
                padding: '11px 22px', fontSize: '0.88rem', fontWeight: '700',
                cursor: isBatchRunning || pendingCount === 0 ? 'not-allowed' : 'pointer',
                fontFamily: 'Inter, sans-serif', whiteSpace: 'nowrap',
              }}
            >
              {isBatchRunning ? '⏳ Summarizing…' : '📋 Summarize All'}
            </button>
          </div>
        </div>

        {/* Embed progress bar */}
        {state && (state.running || state.last_status !== 'idle') && (
          <div style={{ marginTop: '16px' }}>
            <div style={{ background: '#0F1117', borderRadius: '8px', height: '8px', overflow: 'hidden' }}>
              <div style={{
                width: `${state.progress || 0}%`, height: '100%',
                background: state.last_status === 'failed' ? '#EF4444' : '#FF6B00',
                transition: 'width 0.4s ease',
              }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px' }}>
              <span style={{ color: '#7A7F94', fontSize: '0.78rem' }}>{state.last_message}</span>
              <span style={{ color: '#555', fontSize: '0.78rem', fontFamily: 'monospace' }}>{state.progress || 0}%</span>
            </div>
          </div>
        )}

        {/* Batch summary progress bar */}
        {batchState && (batchState.running || batchState.last_status !== 'idle') && (
          <div style={{ marginTop: '16px' }}>
            <div style={{ background: '#0F1117', borderRadius: '8px', height: '8px', overflow: 'hidden' }}>
              <div style={{
                width: `${batchState.progress || 0}%`, height: '100%',
                background: batchState.last_status === 'failed' ? '#EF4444' : '#FACC15',
                transition: 'width 0.4s ease',
              }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px' }}>
              <span style={{ color: '#7A7F94', fontSize: '0.78rem' }}>{batchState.last_message}</span>
              <span style={{ color: '#555', fontSize: '0.78rem', fontFamily: 'monospace' }}>{batchState.progress || 0}%</span>
            </div>
          </div>
        )}
      </div>

      {/* Document list */}
      <div style={{ color: '#B0B4C8', fontSize: '0.9rem', fontWeight: '600', marginBottom: '10px' }}>
        Documents ({files.length})
      </div>

      {loading && (
        <div style={{ color: '#555', fontSize: '0.85rem', padding: '20px 0' }}>Loading…</div>
      )}

      {!loading && files.length === 0 && (
        <div style={{ color: '#555', fontSize: '0.85rem', padding: '20px 0', fontStyle: 'italic' }}>
          No documents uploaded yet. Go to Upload GR to add some.
        </div>
      )}

      {!loading && files.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {files.map((f, i) => (
            <div key={i} style={{
              background: '#1A1D2E', border: '1px solid #2A2D3E', borderRadius: '10px',
              padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', overflow: 'hidden' }}>
                <span style={{ fontSize: '1.2rem', flexShrink: 0 }}>📄</span>
                <div style={{ overflow: 'hidden' }}>
                  <div style={{
                    color: '#E8EAF0', fontSize: '0.85rem', fontWeight: '600',
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  }}>
                    {f.filename}
                  </div>
                  <div style={{ color: '#555', fontSize: '0.72rem', fontFamily: 'monospace', marginTop: '2px' }}>
                    {f.page_count ?? '?'} pages
                    {!f.exists_on_disk && (
                      <span style={{ color: '#EF4444', marginLeft: '8px' }}>⚠ missing from disk</span>
                    )}
                  </div>
                </div>
              </div>

              <span style={{
                fontSize: '0.7rem', padding: '3px 10px', borderRadius: '12px',
                fontFamily: 'monospace', flexShrink: 0,
                color: f.embedded ? '#4ADE80' : '#FACC15',
                background: f.embedded ? '#0F2A1A' : '#2A2410',
                border: `1px solid ${f.embedded ? '#4ADE8033' : '#FACC1533'}`,
              }}>
                {f.embedded ? '✓ Embedded' : '○ Pending'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}