import { useCallback, useEffect, useState } from "react"
import ChatInterface from "./components/ChatInterface"
import ChatSidebar from "./components/ChatSidebar"
import DocumentLibrary from "./components/DocumentLibrary"
import UploadArea from "./components/UploadArea"

const C = { primary: "#003371", primary2: "#00499c" }

export default function App() {
  const [view, setView] = useState("chat")
  const [sessions, setSessions] = useState([])
  const [documents, setDocuments] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)

  const isReady = documents.some(d => d.status === "indexed")

  const fetchDocuments = useCallback(async () => {
    try {
      const res = await fetch("/api/documents")
      const data = await res.json()
      setDocuments(data.documents ?? [])
    } catch (e) { console.error(e) }
  }, [])

  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch("/api/sessions")
      setSessions((await res.json()) ?? [])
    } catch (e) { console.error(e) }
  }, [])

  useEffect(() => { fetchDocuments(); fetchSessions() }, [fetchDocuments, fetchSessions])

  useEffect(() => {
    const inFlight = documents.filter(d => d.status === "pending" || d.status === "processing")
    if (!inFlight.length) return
    const id = setInterval(fetchDocuments, 2500)
    return () => clearInterval(id)
  }, [documents, fetchDocuments])

  const handleDelete = async (docId) => {
    await fetch(`/api/documents/${docId}`, { method: "DELETE" })
    setDocuments(prev => prev.filter(d => d.id !== docId))
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden" style={{ background: "#f7f9fb" }}>
      <ChatSidebar
        sessions={sessions}
        documents={documents}
        activeView={view}
        activeSessionId={activeSessionId}
        onSelectSession={(id) => { setActiveSessionId(id); setView("chat") }}
        onNew={() => { setActiveSessionId(null); setView("chat") }}
        onNavigate={setView}
      />

      {/* Right of sidebar */}
      <div className="flex flex-col flex-1 min-w-0" style={{ marginLeft: "16rem" }}>

        {/* ── Top header ── */}
        <header
          className="fixed top-0 right-0 h-16 flex items-center justify-between px-8 z-40"
          style={{
            left: "16rem",
            background: "rgba(255,255,255,0.85)",
            backdropFilter: "blur(12px)",
            borderBottom: "1px solid rgba(226,232,240,0.6)",
          }}
        >
          {/* Context tabs */}
          <nav className="flex items-center gap-6 h-full">
            {[["chat", "Research Chat"], ["upload", "Knowledge Ingestion"]].map(([key, label]) => (
              <button
                key={key}
                onClick={() => setView(key)}
                className="h-full text-sm font-semibold border-b-2 transition-colors"
                style={{
                  borderColor: view === key ? C.primary : "transparent",
                  color: view === key ? C.primary : "#94a3b8",
                }}
              >
                {label}
              </button>
            ))}
          </nav>

          {/* Right actions */}
          <div className="flex items-center gap-3">
            <div className="relative">
              <span
                className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2"
                style={{ fontSize: "18px", color: "#94a3b8" }}
              >
                search
              </span>
              <input
                type="text"
                placeholder="Search knowledge base..."
                className="rounded-lg py-2 pl-9 pr-4 text-sm w-56 outline-none transition-all"
                style={{ background: "#f1f5f9", color: "#334155" }}
                onFocus={e => e.currentTarget.style.boxShadow = `0 0 0 2px ${C.primary}33`}
                onBlur={e => e.currentTarget.style.boxShadow = "none"}
              />
            </div>
            <button
              className="w-9 h-9 flex items-center justify-center rounded-lg transition-colors"
              style={{ color: "#94a3b8" }}
              onMouseEnter={e => e.currentTarget.style.color = C.primary}
              onMouseLeave={e => e.currentTarget.style.color = "#94a3b8"}
            >
              <span className="material-symbols-outlined" style={{ fontSize: "22px" }}>notifications</span>
            </button>
            <button
              className="w-9 h-9 flex items-center justify-center rounded-lg transition-colors"
              style={{ color: "#94a3b8" }}
              onMouseEnter={e => e.currentTarget.style.color = C.primary}
              onMouseLeave={e => e.currentTarget.style.color = "#94a3b8"}
            >
              <span className="material-symbols-outlined" style={{ fontSize: "22px" }}>help_outline</span>
            </button>
            <button
              onClick={() => setView("upload")}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-bold text-white transition-all hover:opacity-90 active:scale-[0.98]"
              style={{ background: `linear-gradient(135deg, ${C.primary} 0%, ${C.primary2} 100%)` }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>upload</span>
              Upload
            </button>
          </div>
        </header>

        {/* ── Page content ── */}
        <div className="flex-1 overflow-hidden" style={{ paddingTop: "4rem" }}>

          {/* Chat */}
          {view === "chat" && (
            <ChatInterface
              sessionId={activeSessionId}
              isReady={isReady}
              onSessionCreated={fetchSessions}
              onGoToUpload={() => setView("upload")}
            />
          )}

          {/* Upload / Knowledge Ingestion */}
          {view === "upload" && (
            <div className="h-full overflow-y-auto custom-scrollbar">
              <div className="max-w-6xl mx-auto px-10 py-10">

                {/* Page header */}
                <div className="mb-10">
                  <h2 className="text-3xl font-extrabold tracking-tight" style={{ color: "#191c1e" }}>
                    Knowledge Ingestion
                  </h2>
                  <p className="mt-2 max-w-2xl leading-relaxed text-sm" style={{ color: "#434652" }}>
                    Upload your research papers, legal contracts, or technical manuals.
                    Our AI will index the content for instant contextual retrieval.
                  </p>
                </div>

                {/* Bento grid */}
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">

                  {/* Left — upload zone (8 cols) */}
                  <div className="lg:col-span-8 space-y-6">
                    <UploadArea onUploadComplete={fetchDocuments} />

                    {/* Pro tip */}
                    <div
                      className="rounded-xl p-5 flex gap-4 items-start"
                      style={{ background: "#f2f4f6" }}
                    >
                      <span className="material-symbols-outlined shrink-0" style={{ color: "#602100", fontSize: "22px" }}>info</span>
                      <div>
                        <p className="text-sm font-semibold" style={{ color: "#191c1e" }}>Pro Tip: Multi-File Context</p>
                        <p className="text-sm mt-1 leading-relaxed" style={{ color: "#434652" }}>
                          Uploading related documents together allows the AI to draw cross-references
                          and build a more robust intelligence graph for your queries.
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Right — library + stats (4 cols) */}
                  <div className="lg:col-span-4 space-y-6">
                    <DocumentLibrary documents={documents} onDelete={handleDelete} />

                    {/* Storage / index stats */}
                    <div
                      className="rounded-xl p-6 text-white relative overflow-hidden"
                      style={{ background: C.primary }}
                    >
                      <p className="text-[10px] font-bold uppercase tracking-[0.2em] mb-4" style={{ color: "rgba(255,255,255,0.55)" }}>
                        Index Coverage
                      </p>
                      <div className="flex items-end justify-between mb-2">
                        <span className="text-3xl font-black">
                          {documents.length === 0
                            ? "—"
                            : `${Math.round((documents.filter(d => d.status === "indexed").length / documents.length) * 100)}%`}
                        </span>
                        <span className="text-sm" style={{ color: "rgba(255,255,255,0.7)" }}>
                          {documents.filter(d => d.status === "indexed").length} / {documents.length} docs
                        </span>
                      </div>
                      <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.2)" }}>
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            background: "white",
                            width: documents.length === 0
                              ? "0%"
                              : `${(documents.filter(d => d.status === "indexed").length / documents.length) * 100}%`,
                          }}
                        />
                      </div>
                      <p className="text-xs mt-4" style={{ color: "rgba(255,255,255,0.6)" }}>
                        {documents.length === 0
                          ? "Upload documents to get started"
                          : documents.some(d => d.status === "processing" || d.status === "pending")
                          ? "Processing — model download may take a moment"
                          : documents.some(d => d.status === "failed")
                          ? "Some documents failed — re-upload to retry"
                          : `All ${documents.length} document${documents.length > 1 ? "s" : ""} indexed and ready`}
                      </p>
                    </div>
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
