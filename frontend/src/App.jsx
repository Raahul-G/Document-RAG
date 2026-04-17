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

  // Fetch documents from API
  const fetchDocuments = useCallback(async () => {
    try {
      const res = await fetch("/api/documents")
      const data = await res.json()
      setDocuments(data.documents ?? [])
    } catch (e) {
      console.error("Failed to fetch documents:", e)
    }
  }, [])

  useEffect(() => { fetchDocuments() }, [fetchDocuments])

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
        activeView={view}
        activeSessionId={activeSessionId}
        onSelectSession={(id) => { setActiveSessionId(id); setView("chat") }}
        onNew={() => { setActiveSessionId(null); setView("chat") }}
        onNavigate={setView}
      />

      <div className="flex flex-col flex-1 min-w-0">
        {/* Header */}
        <header className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200 shrink-0">
          <div className="flex items-center gap-6">
            <span className="text-base font-semibold" style={{ color: "#0D1B3E" }}>Document RAG</span>
            <nav className="flex items-center gap-1">
              <TabButton active={view === "chat"} onClick={() => setView("chat")}>Research Chat</TabButton>
              <TabButton active={view === "upload"} onClick={() => setView("upload")}>Repository</TabButton>
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm" style={{ borderColor: "#E2E8F0", background: "#F5F7FA" }}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <circle cx="6" cy="6" r="4.5" stroke="#9CA3AF" strokeWidth="1.3" />
                <path d="M10.5 10.5L13 13" stroke="#9CA3AF" strokeWidth="1.3" strokeLinecap="round" />
              </svg>
              <input type="text" placeholder="Global search..." className="bg-transparent outline-none w-36 text-xs" style={{ color: "#6B7280" }} />
            </div>

            <button className="w-8 h-8 flex items-center justify-center rounded-lg border transition-colors" style={{ borderColor: "#E2E8F0" }}
              onMouseEnter={e => e.currentTarget.style.background = "#F5F7FA"}
              onMouseLeave={e => e.currentTarget.style.background = "transparent"}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M8 2a4.5 4.5 0 00-4.5 4.5v2L2 10h12l-1.5-1.5v-2A4.5 4.5 0 008 2zM6.5 12a1.5 1.5 0 003 0" stroke="#6B7280" strokeWidth="1.3" strokeLinecap="round" />
              </svg>
            </button>

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
              Upload Document
            </button>
          </div>
        </header>

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          {view === "chat" && <ChatInterface sessionId={activeSessionId} />}

          {view === "upload" && (
            <div className="h-full overflow-y-auto p-6">
              <div className="flex gap-6">
                {/* Left column */}
                <div className="flex-1 min-w-0 space-y-6">
                  <div>
                    <h1 className="text-xl font-bold" style={{ color: "#0D1B3E" }}>Document Repository</h1>
                    <p className="text-sm mt-1" style={{ color: "#6B7280" }}>
                      Manage your knowledge base. Uploaded documents are automatically chunked
                      and indexed for high-precision retrieval during research sessions.
                    </p>
                  </div>
                  <UploadArea onUploadComplete={fetchDocuments} />
                  <DocumentLibrary documents={documents} onDelete={handleDelete} />
                </div>

                {/* Right column */}
                <div className="w-64 shrink-0 space-y-4">
                  {/* System health card */}
                  <div className="rounded-xl p-5 text-white" style={{ background: "#0D1B3E" }}>
                    <p className="text-[10px] font-semibold tracking-widest uppercase mb-4" style={{ color: "#9CA3AF" }}>System Health</p>
                    <p className="text-4xl font-bold">
                      {documents.length === 0 ? "—" : `${Math.round((documents.filter(d => d.status === "indexed").length / documents.length) * 100)}%`}
                    </p>
                    <p className="text-[10px] tracking-widest uppercase mt-1 mb-4" style={{ color: "#9CA3AF" }}>Indexed</p>
                    <div className="h-1 rounded-full mb-4" style={{ background: "#1E3A6E" }}>
                      <div
                        className="h-1 rounded-full transition-all"
                        style={{
                          background: "#EEF2FF",
                          width: documents.length === 0 ? "0%" : `${(documents.filter(d => d.status === "indexed").length / documents.length) * 100}%`,
                        }}
                      />
                    </div>
                    <div className="flex justify-between">
                      <div>
                        <p className="text-lg font-semibold">{documents.length}</p>
                        <p className="text-[10px] tracking-wider uppercase" style={{ color: "#9CA3AF" }}>Documents</p>
                      </div>
                      <div>
                        <p className="text-lg font-semibold">{documents.filter(d => d.status === "indexed").length}</p>
                        <p className="text-[10px] tracking-wider uppercase" style={{ color: "#9CA3AF" }}>Indexed</p>
                      </div>
                    </div>
                  </div>

                  {/* Status card */}
                  <div className="rounded-xl p-4 bg-white border border-gray-200">
                    <div className="flex items-center gap-2.5 mb-3">
                      <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: "#0D1B3E" }}>
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                          <circle cx="7" cy="7" r="5" stroke="white" strokeWidth="1.3" />
                          <path d="M7 4.5v3l2 1.5" stroke="white" strokeWidth="1.3" strokeLinecap="round" />
                        </svg>
                      </div>
                      <p className="text-sm font-semibold" style={{ color: "#0D1B3E" }}>Index Status</p>
                    </div>
                    <p className="text-xs leading-relaxed" style={{ color: "#6B7280" }}>
                      {documents.length === 0
                        ? "No documents yet. Upload a PDF or DOCX to get started."
                        : documents.some(d => d.status === "processing" || d.status === "pending")
                        ? "Processing documents — this may take a moment on first run (model download)."
                        : documents.some(d => d.status === "failed")
                        ? "Some documents failed to index. Remove and re-upload to retry."
                        : `All ${documents.length} document${documents.length > 1 ? "s" : ""} indexed and ready for search.`}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function TabButton({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className="px-3 py-1.5 text-sm font-medium transition-colors relative"
      style={{ color: active ? "#003499" : "#9CA3AF" }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.color = "#374151" }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.color = active ? "#003499" : "#9CA3AF" }}
    >
      {children}
      {active && <span className="absolute bottom-0 left-0 right-0 h-0.5 rounded-full" style={{ background: "#003499" }} />}
    </button>
  )
}
