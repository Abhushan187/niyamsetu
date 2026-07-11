// frontend/src/components/CitationPill.jsx
// ─────────────────────────────────────────────────────────
// Small pill tag shown below every AI answer.
// Displays which file and page the answer came from.
// Example: 📄 GR_2024_transfer.pdf — p.3
// ─────────────────────────────────────────────────────────

export default function CitationPill({ file, page }) {
  return (
    <span style={{
      background: '#0D2137',
      border: '1px solid #1E3A5F',
      color: '#6FB3FF',
      padding: '3px 12px',
      borderRadius: '20px',
      fontSize: '0.75rem',
      fontFamily: 'monospace',
      whiteSpace: 'nowrap',
    }}>
      📄 {file} — p.{page}
    </span>
  )
}