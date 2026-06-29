import { useRef, useState } from "react"

const C = { primary: "#003371", primary2: "#00499c" }

const ALLOWED_MIME = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]

const STAGE_LABELS = {
  waiting:   { label: "Queued",    color: "#F59E0B" },
  parsing:   { label: "Parsing",   color: "#F59E0B" },
  chunking:  { label: "Chunking",  color: "#F59E0B" },
  embedding: { label: "Embedding", color: "#F59E0B" },
  storing:   { label: "Storing",   color: "#F59E0B" },
  done:      { label: "Indexed",   color: "#16A34A" },
  failed:    { label: "Failed",    color: "#DC2626" },
}

export default function UploadArea({ onUploadComplete }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [uploads, setUploads] = useState([])

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
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files) }}
        className="rounded-2xl border-2 border-dashed py-14 px-8 flex flex-col items-center gap-5 transition-all cursor-pointer"
        style={{
          borderColor: dragging ? C.primary : "rgba(0,51,113,0.2)",
          background: dragging ? "#dbeafe" : "white",
        }}
        onClick={() => inputRef.current?.click()}
      >
        {/* Icon */}
        <div
          className="w-20 h-20 rounded-full flex items-center justify-center"
          style={{ background: "#dbeafe" }}
        >
          <span
            className="material-symbols-outlined"
            style={{ fontSize: "40px", color: C.primary, fontVariationSettings: "'FILL' 1" }}
          >
            cloud_upload
          </span>
        </div>

        {/* Text */}
        <div className="text-center">
          <p className="font-bold text-base" style={{ color: "#191c1e" }}>
            Drag and drop files here
          </p>
          <p className="text-sm mt-1.5" style={{ color: "#64748b" }}>
            or click to browse — PDF and DOCX, up to 50 MB each
          </p>
        </div>

        {/* CTA buttons */}
        <div className="flex items-center gap-3" onClick={e => e.stopPropagation()}>
          <button
            onClick={() => inputRef.current?.click()}
            className="flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-bold text-white transition-all hover:opacity-90 active:scale-[0.97]"
            style={{ background: `linear-gradient(135deg, ${C.primary} 0%, ${C.primary2} 100%)` }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>upload_file</span>
            Browse Files
          </button>
        </div>

        {/* File type badges */}
        <div className="flex items-center gap-2">
          {["PDF", "DOCX"].map(type => (
            <span
              key={type}
              className="text-[11px] px-2.5 py-1 rounded-full font-semibold border"
              style={{ background: "#eef2ff", color: C.primary, borderColor: "#c5d4fe" }}
            >
              {type}
            </span>
          ))}
          <span className="text-[11px]" style={{ color: "#94a3b8" }}>Supported formats</span>
        </div>

        <p className="text-[11px]" style={{ color: "#94a3b8" }}>🛡️ 100% Local &amp; Private</p>

        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.docx"
          className="hidden"
          onChange={e => handleFiles(e.target.files)}
        />
      </div>

      {/* Upload progress list */}
      {uploads.length > 0 && (
        <div
          className="rounded-xl border overflow-hidden"
          style={{ background: "white", borderColor: "rgba(226,232,240,0.8)" }}
        >
          {/* Header */}
          <div
            className="flex items-center justify-between px-5 py-3"
            style={{ borderBottom: "1px solid rgba(226,232,240,0.6)" }}
          >
            <div className="flex items-center gap-2">
              <span
                className="material-symbols-outlined"
                style={{ fontSize: "16px", color: C.primary }}
              >
                upload
              </span>
              <span className="text-xs font-bold" style={{ color: "#191c1e" }}>
                Upload Progress
              </span>
            </div>
            {uploads.some(u => u.done) && (
              <button
                onClick={clearDone}
                className="text-xs font-medium transition-colors"
                style={{ color: "#94a3b8" }}
                onMouseEnter={e => e.currentTarget.style.color = C.primary}
                onMouseLeave={e => e.currentTarget.style.color = "#94a3b8"}
              >
                Clear completed
              </button>
            )}
          </div>

          {/* Rows */}
          {uploads.map(u => {
            const s = STAGE_LABELS[u.stage] ?? STAGE_LABELS.waiting
            const isPdf = u.name.toLowerCase().endsWith(".pdf")
            return (
              <div
                key={u.uid}
                className="flex items-center gap-3 px-5 py-3.5"
                style={{ borderTop: "1px solid rgba(226,232,240,0.4)" }}
              >
                {/* File type icon */}
                <div
                  className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                  style={{ background: "#f1f5f9" }}
                >
                  <span
                    className="material-symbols-outlined"
                    style={{
                      fontSize: "18px",
                      color: isPdf ? "#dc2626" : "#003371",
                      fontVariationSettings: "'FILL' 1",
                    }}
                  >
                    {isPdf ? "picture_as_pdf" : "description"}
                  </span>
                </div>

                {/* File info */}
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold truncate" style={{ color: "#191c1e" }}>
                    {u.name}
                  </p>
                  <p
                    className="text-[11px] mt-0.5 truncate"
                    style={{ color: u.error ? "#dc2626" : "#94a3b8" }}
                  >
                    {u.message}
                  </p>
                </div>

                {/* Status indicator */}
                <div className="shrink-0 flex items-center gap-1.5">
                  {u.done && !u.error ? (
                    <span
                      className="material-symbols-outlined"
                      style={{ fontSize: "18px", color: "#16a34a", fontVariationSettings: "'FILL' 1" }}
                    >
                      check_circle
                    </span>
                  ) : u.error ? (
                    <span
                      className="material-symbols-outlined"
                      style={{ fontSize: "18px", color: "#dc2626", fontVariationSettings: "'FILL' 1" }}
                    >
                      cancel
                    </span>
                  ) : (
                    <svg className="animate-spin" width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <circle cx="8" cy="8" r="6" stroke="#e2e8f0" strokeWidth="2" />
                      <path d="M8 2a6 6 0 016 6" stroke={C.primary} strokeWidth="2" strokeLinecap="round" />
                    </svg>
                  )}
                  <span className="text-[11px] font-semibold" style={{ color: s.color }}>
                    {s.label}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
