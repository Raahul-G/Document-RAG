import { useCallback, useEffect, useState } from "react"
import ChatInterface from "./components/ChatInterface"
import ChatSidebar from "./components/ChatSidebar"
import DocumentLibrary from "./components/DocumentLibrary"
import UploadArea from "./components/UploadArea"

export default function App() {
  const [view, setView] = useState("chat")
  const [sessions, setSessions] = useState([])
  const [documents, setDocuments] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)

  // Derived: at least one indexed doc enables chat
  const isReady = documents.some(d => d.status === "indexed")

  const fetchDocuments = useCallback(async () => {
    try {
      const res = await fetch("/api/documents")
      const data = await res.json()
      setDocuments(data.documents ?? [])
    } catch (e) {
      console.error("Failed to fetch documents:", e)
    }
  }, [])

  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch("/api/sessions")
      const data = await res.json()
      setSessions(data ?? [])
    } catch (e) {
      console.error("Failed to fetch sessions:", e)
    }
  }, [])

  useEffect(() => {
    fetchDocuments()
    fetchSessions()
  }, [fetchDocuments, fetchSessions])

  // Poll while any document is still processing
  useEffect(() => {
    const inFlight = documents.filter(d => d.status === "pending" || d.status === "processing")
    if (inFlight.length === 0) return
    const id = setInterval(fetchDocuments, 2500)
    return () => clearInterval(id)
  }, [documents, fetchDocuments])

  const handleDelete = async (docId) => {
    await fetch(`/api/documents/${docId}`, { method: "DELETE" })
    setDocuments(prev => prev.filter(d => d.id !== docId))
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden" style={{ background: "#F5F7FA" }}>
      <ChatSidebar
        sessions={sessions}
        documents={documents}
        activeView={view}
        activeSessionId={activeSessionId}
        onSelectSession={(id) => { setActiveSessionId(id); setView("chat") }}
        onNew={() => { setActiveSessionId(null); setView("chat") }}
        onNavigate={setView}
      />

      <div className="flex flex-col flex-1 min-w-0">
        {/* Minimal header — no duplicate tab nav */}
        <header className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200 shrink-0">
          <span className="text-base font-semibold" style={{ color: "#0D1B3E" }}>
            {view === "chat" ? "Research Chat" : "Document Repository"}
          </span>

          <button
            onClick={() => setView("upload")}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white transition-colors"
            style={{ background: "#003499" }}
            onMouseEnter={e => e.currentTarget.style.background = "#002580"}
            onMouseLeave={e => e.currentTarget.style.background = "#003499"}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M7 9V3M7 3L4.5 5.5M7 3L9.5 5.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M2 11h10" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            Upload
          </button>
        </header>

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          {view === "chat" && (
            <ChatInterface
              sessionId={activeSessionId}
              isReady={isReady}
              onSessionCreated={fetchSessions}
              onGoToUpload={() => setView("upload")}
            />
          )}

          {view === "upload" && (
            <div className="h-full overflow-y-auto py-8">
              <div className="max-w-4xl mx-auto px-8 space-y-7">

                {/* Page header */}
                <div>
                  <h1 className="text-2xl font-bold tracking-tight" style={{ color: "#0D1B3E" }}>
                    Document Repository
                  </h1>
                  <p className="text-sm mt-1.5 max-w-xl" style={{ color: "#6B7280" }}>
                    Uploaded documents are automatically chunked and indexed for
                    high-precision retrieval. Supports PDF and DOCX.
                  </p>
                </div>

                {/* Stats row */}
                <RepositoryStats documents={documents} />

                {/* Upload + library */}
                <UploadArea onUploadComplete={fetchDocuments} />
                <DocumentLibrary documents={documents} onDelete={handleDelete} />

              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function RepositoryStats({ documents }) {
  const total = documents.length
  const indexed = documents.filter(d => d.status === "indexed").length
  const processing = documents.some(d => d.status === "processing" || d.status === "pending")
  const failed = documents.some(d => d.status === "failed")
  const pct = total === 0 ? 0 : Math.round((indexed / total) * 100)

  const statusLabel = processing
    ? "Processing…"
    : failed
    ? "Action needed"
    : indexed > 0
    ? "Ready for search"
    : "Upload to start"

  const statusColor = processing ? "#F59E0B" : failed ? "#DC2626" : indexed > 0 ? "#16A34A" : "#9CA3AF"

  return (
    <div className="grid grid-cols-3 gap-4">
      {/* Total */}
      <div className="bg-white rounded-xl border border-gray-200 px-5 py-4">
        <p className="text-[11px] font-semibold uppercase tracking-widest mb-3" style={{ color: "#9CA3AF" }}>
          Documents
        </p>
        <p className="text-3xl font-bold" style={{ color: "#0D1B3E" }}>{total || "—"}</p>
        <p className="text-xs mt-1" style={{ color: "#9CA3AF" }}>Total uploaded</p>
      </div>

      {/* Indexed */}
      <div className="bg-white rounded-xl border border-gray-200 px-5 py-4">
        <p className="text-[11px] font-semibold uppercase tracking-widest mb-3" style={{ color: "#9CA3AF" }}>
          Indexed
        </p>
        <p className="text-3xl font-bold" style={{ color: "#003499" }}>{total === 0 ? "—" : indexed}</p>
        <p className="text-xs mt-1" style={{ color: "#9CA3AF" }}>Ready for search</p>
      </div>

      {/* Status */}
      <div className="rounded-xl px-5 py-4" style={{ background: "#0D1B3E" }}>
        <p className="text-[11px] font-semibold uppercase tracking-widest mb-3" style={{ color: "#4A6FA5" }}>
          Coverage
        </p>
        <p className="text-3xl font-bold text-white">{total === 0 ? "—" : `${pct}%`}</p>
        <div className="flex items-center gap-1.5 mt-1">
          <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: statusColor }} />
          <p className="text-xs" style={{ color: "#9CA3AF" }}>{statusLabel}</p>
        </div>
      </div>
    </div>
  )
}
