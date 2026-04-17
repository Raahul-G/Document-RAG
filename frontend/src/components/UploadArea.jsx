import { useRef, useState } from "react"

const ALLOWED_MIME = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]

const STAGE_LABELS = {
  waiting:   { label: "Queued",     color: "#9CA3AF" },
  parsing:   { label: "Parsing",    color: "#F59E0B" },
  chunking:  { label: "Chunking",   color: "#F59E0B" },
  embedding: { label: "Embedding",  color: "#F59E0B" },
  storing:   { label: "Storing",    color: "#F59E0B" },
  done:      { label: "Indexed ✓",  color: "#16A34A" },
  failed:    { label: "Failed",     color: "#DC2626" },
}

export default function UploadArea({ onUploadComplete }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [uploads, setUploads] = useState([]) // [{uid, name, stage, message, done, error}]

  const setUploadField = (uid, fields) =>
    setUploads(prev => prev.map(u => u.uid === uid ? { ...u, ...fields } : u))

  const handleFiles = async (files) => {
    const valid = Array.from(files).filter(f => ALLOWED_MIME.includes(f.type))
    if (!valid.length) return

    for (const file of valid) {
      const uid = `${Date.now()}-${Math.random()}`
      setUploads(prev => [...prev, { uid, name: file.name, stage: "waiting", message: "Uploading...", done: false, error: null }])

      try {
        const form = new FormData()
        form.append("file", file)

        const res = await fetch("/api/documents/upload", { method: "POST", body: form })

        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: "Upload failed" }))
          setUploadField(uid, { stage: "failed", message: err.detail, done: true, error: err.detail })
          continue
        }

        const doc = await res.json()

        // Connect to SSE progress stream
        const es = new EventSource(`/api/documents/${doc.id}/progress`)

        es.onmessage = (e) => {
          const p = JSON.parse(e.data)
          setUploadField(uid, { stage: p.stage, message: p.message, done: !!p.done, error: p.error })
          if (p.done || p.error) {
            es.close()
            onUploadComplete?.()
          }
        }

        es.onerror = () => {
          es.close()
          setUploadField(uid, { stage: "failed", message: "Lost connection to server.", done: true, error: "Connection error" })
        }

      } catch (err) {
        setUploadField(uid, { stage: "failed", message: err.message, done: true, error: err.message })
      }
    }
  }

  const clearDone = () => setUploads(prev => prev.filter(u => !u.done))

  return (
    <div className="space-y-3">
      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files) }}
        className="rounded-xl border border-dashed py-10 flex flex-col items-center gap-4 transition-colors"
        style={{ borderColor: dragging ? "#003499" : "#C7D7F5", background: dragging ? "#EEF2FF" : "#FAFBFF" }}
      >
        <div className="w-14 h-14 rounded-2xl flex items-center justify-center" style={{ background: "#EEF2FF" }}>
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
            <path d="M12 16V8M12 8L9 11M12 8L15 11" stroke="#003499" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M20 16.5A4.5 4.5 0 0016 12H15a7 7 0 10-11.95 5" stroke="#003499" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </div>
        <div className="text-center">
          <p className="text-sm font-semibold" style={{ color: "#0D1B3E" }}>Upload knowledge assets</p>
          <p className="text-xs mt-1" style={{ color: "#6B7280" }}>Drag and drop PDF or DOCX files. Max 50 MB per document.</p>
        </div>
        <button
          onClick={() => inputRef.current?.click()}
          className="px-5 py-2 rounded-lg text-sm font-medium border transition-colors"
          style={{ borderColor: "#003499", color: "#003499", background: "white" }}
          onMouseEnter={e => e.currentTarget.style.background = "#EEF2FF"}
          onMouseLeave={e => e.currentTarget.style.background = "white"}
        >
          Select Files
        </button>
        <input ref={inputRef} type="file" multiple accept=".pdf,.docx" className="hidden" onChange={e => handleFiles(e.target.files)} />
      </div>

      {/* Upload progress list */}
      {uploads.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100">
            <span className="text-xs font-semibold" style={{ color: "#6B7280" }}>Upload Progress</span>
            {uploads.some(u => u.done) && (
              <button onClick={clearDone} className="text-xs transition-colors" style={{ color: "#9CA3AF" }}
                onMouseEnter={e => e.currentTarget.style.color = "#003499"}
                onMouseLeave={e => e.currentTarget.style.color = "#9CA3AF"}
              >
                Clear completed
              </button>
            )}
          </div>

          {uploads.map(u => {
            const s = STAGE_LABELS[u.stage] ?? STAGE_LABELS.waiting
            return (
              <div key={u.uid} className="flex items-center gap-3 px-4 py-3 border-b border-gray-50 last:border-0">
                {/* Spinner or done icon */}
                <div className="shrink-0 w-5 h-5 flex items-center justify-center">
                  {u.done && !u.error ? (
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <circle cx="8" cy="8" r="7" fill="#16A34A" />
                      <path d="M5 8l2 2 4-4" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  ) : u.error ? (
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <circle cx="8" cy="8" r="7" fill="#DC2626" />
                      <path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                  ) : (
                    <svg className="animate-spin" width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <circle cx="8" cy="8" r="6" stroke="#E2E8F0" strokeWidth="2" />
                      <path d="M8 2a6 6 0 016 6" stroke="#003499" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                  )}
                </div>

                {/* File info */}
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium truncate" style={{ color: "#0D1B3E" }}>{u.name}</p>
                  <p className="text-[11px] truncate" style={{ color: u.error ? "#DC2626" : "#9CA3AF" }}>{u.message}</p>
                </div>

                {/* Stage badge */}
                <span className="text-[11px] font-semibold shrink-0" style={{ color: s.color }}>
                  {s.label}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
