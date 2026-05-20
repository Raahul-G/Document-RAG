import { useEffect, useRef, useState } from "react"

const THINKING_PHASES = [
  { label: "Thinking",           icon: "psychology"     },
  { label: "Searching documents",icon: "manage_search"  },
  { label: "Analyzing",          icon: "analytics"      },
  { label: "Preparing answer",   icon: "edit_note"      },
]
import { createPortal } from "react-dom"

const C = { primary: "#003371", primary2: "#00499c" }


export default function ChatInterface({ sessionId, isReady, onSessionCreated, onGoToUpload }) {
  const [question, setQuestion] = useState("")
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [currentSessionId, setCurrentSessionId] = useState(sessionId)
  const [activeSources, setActiveSources] = useState([])
  const [snippetModal, setSnippetModal] = useState(null)
  const [copySuccess, setCopySuccess] = useState(false)
  const [thinkingPhase, setThinkingPhase] = useState(0)
  const bottomRef = useRef(null)

  // Cycle thinking phases while the streaming bubble has no text yet
  const isWaiting = messages.some(m => m.streaming && !m.text)
  useEffect(() => {
    if (!isWaiting) { setThinkingPhase(0); return }
    const id = setInterval(() => {
      setThinkingPhase(p => (p + 1) % THINKING_PHASES.length)
    }, 1600)
    return () => clearInterval(id)
  }, [isWaiting])

  // Load session history when sidebar selection changes
  useEffect(() => {
    setCurrentSessionId(sessionId)
    if (!sessionId) { setMessages([]); setActiveSources([]); return }
    fetch(`/api/sessions/${sessionId}`)
      .then(r => r.json())
      .then(data => {
        const msgs = []
        let lastSources = []
        for (const m of (data.messages ?? [])) {
          msgs.push({ type: "question", text: m.question })
          const sources = JSON.parse(m.sources_json ?? "[]")
          if (sources.length > 0) lastSources = sources
          msgs.push({
            type: "answer",
            text: m.answer || "I could not find an answer to this question in the uploaded documents.",
            sources,
            found: !!m.answer,
          })
        }
        setMessages(msgs)
        setActiveSources(lastSources)
      })
      .catch(console.error)
  }, [sessionId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

  const handleSubmit = async (e) => {
    e?.preventDefault()
    if (!question.trim() || loading || !isReady) return
    const q = question.trim()
    setQuestion("")
    setMessages(prev => [...prev, { type: "question", text: q }])
    setLoading(true)

    // Insert a streaming placeholder immediately so the user sees the bubble appear
    setMessages(prev => [...prev, { type: "answer", text: "", sources: [], found: true, streaming: true }])

    try {
      const res = await fetch("/api/query/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, session_id: currentSessionId ?? null }),
      })
      if (!res.ok) throw new Error(`Request failed (${res.status})`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })

        // SSE lines come in as "data: {...}\n\n"
        const lines = buf.split("\n")
        buf = lines.pop() // keep partial line for next chunk

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          const raw = line.slice(6).trim()
          if (!raw) continue
          let event
          try { event = JSON.parse(raw) } catch { continue }

          if (event.type === "token") {
            // Append token to the streaming placeholder
            setMessages(prev => {
              const msgs = [...prev]
              const last = msgs[msgs.length - 1]
              if (last?.type === "answer" && last.streaming)
                msgs[msgs.length - 1] = { ...last, text: last.text + event.text }
              return msgs
            })
          } else if (event.type === "done") {
            if (!currentSessionId && event.session_id) {
              setCurrentSessionId(event.session_id)
              onSessionCreated?.()
            }
            const sources = event.sources ?? []
            if (sources.length > 0) setActiveSources(sources)
            setMessages(prev => {
              const msgs = [...prev]
              const last = msgs[msgs.length - 1]
              if (last?.type === "answer" && last.streaming)
                msgs[msgs.length - 1] = {
                  type: "answer",
                  text: event.found
                    ? (last.text || event.answer)
                    : "I could not find an answer to this question in the uploaded documents.",
                  sources,
                  found: event.found,
                  streaming: false,
                }
              return msgs
            })
          } else if (event.type === "error") {
            throw new Error(event.message || "The AI service is temporarily unavailable.")
          }
        }
      }
    } catch (err) {
      setMessages(prev => {
        const msgs = [...prev]
        const last = msgs[msgs.length - 1]
        if (last?.type === "answer" && last.streaming)
          msgs[msgs.length - 1] = { type: "answer", text: err.message || "Something went wrong. Please try again.", sources: [], found: false, streaming: false }
        else
          msgs.push({ type: "answer", text: err.message || "Something went wrong. Please try again.", sources: [], found: false })
        return msgs
      })
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit() }
  }

  const handlePillClick = async (src) => {
    setSnippetModal({ src, imageUrl: null, loading: true, error: null })
    const params = new URLSearchParams({
      doc_name: src.doc_name,
      page: String(src.page),
      text: src.text ?? "",
    })
    // passage_index lets the backend look up the exact stored chunk text from
    // the DB, bypassing any LLM-rewritten text that may have arrived in `text`.
    if (src.passage_index != null) {
      params.set("passage_index", String(src.passage_index))
    }
    try {
      const res = await fetch(`/api/snippets/render?${params}`)
      if (res.status === 501) {
        setSnippetModal(prev => prev ? { ...prev, loading: false, error: "docx" } : null)
        return
      }
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `Error ${res.status}`)
      }
      const blob = await res.blob()
      const imageUrl = URL.createObjectURL(blob)
      setSnippetModal(prev => prev ? { ...prev, imageUrl, loading: false } : null)
    } catch (err) {
      setSnippetModal(prev => prev ? { ...prev, loading: false, error: err.message || "Failed to load" } : null)
    }
  }

  const handleModalClose = () => {
    if (snippetModal?.imageUrl) URL.revokeObjectURL(snippetModal.imageUrl)
    setSnippetModal(null)
    setCopySuccess(false)
  }

  const handleCopyImage = async () => {
    if (!snippetModal?.imageUrl) return
    try {
      const res = await fetch(snippetModal.imageUrl)
      const blob = await res.blob()
      await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })])
      setCopySuccess(true)
      setTimeout(() => setCopySuccess(false), 2000)
    } catch {
      // Clipboard API not available — fall back to download
      const a = document.createElement("a")
      a.href = snippetModal.imageUrl
      a.download = `${snippetModal.src.doc_name}_p${snippetModal.src.page}.png`
      a.click()
    }
  }

  return (
    <div className="flex h-full" style={{ background: "#f7f9fb" }}>

      {/* ── Chat column ── */}
      <div className="flex flex-col flex-1 min-w-0">

        {/* Messages */}
        <div className="flex-1 overflow-y-auto custom-scrollbar py-8">
          <div className="max-w-3xl mx-auto px-8 space-y-8">

            {/* Empty state */}
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center gap-5 py-24">
                {!isReady ? (
                  <>
                    <div
                      className="w-16 h-16 rounded-2xl flex items-center justify-center"
                      style={{ background: "#dbeafe" }}
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: "32px", color: C.primary, fontVariationSettings: "'FILL' 1" }}>
                        cloud_upload
                      </span>
                    </div>
                    <div className="text-center max-w-sm">
                      <p className="font-bold text-base" style={{ color: "#191c1e" }}>No documents indexed yet</p>
                      <p className="text-sm mt-2 leading-relaxed" style={{ color: "#64748b" }}>
                        Upload a PDF or DOCX to get started. Answers are sourced
                        strictly from your documents — no internet access.
                      </p>
                      <p className="text-xs mt-3 font-semibold" style={{ color: "#94a3b8" }}>
                        Supported: PDF · DOCX
                      </p>
                    </div>
                    <button
                      onClick={onGoToUpload}
                      className="flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-bold text-white transition-all hover:opacity-90"
                      style={{ background: `linear-gradient(135deg, ${C.primary} 0%, ${C.primary2} 100%)` }}
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>upload</span>
                      Upload Document
                    </button>
                  </>
                ) : (
                  <>
                    <div
                      className="w-14 h-14 rounded-2xl flex items-center justify-center"
                      style={{ background: "#dbeafe" }}
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: "28px", color: C.primary, fontVariationSettings: "'FILL' 1" }}>
                        smart_toy
                      </span>
                    </div>
                    <div className="text-center">
                      <p className="font-bold text-base" style={{ color: "#191c1e" }}>Ask your documents anything</p>
                      <p className="text-sm mt-1.5 max-w-sm" style={{ color: "#64748b" }}>
                        Answers come strictly from your uploaded documents. No internet access.
                      </p>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Message bubbles */}
            {messages.map((msg, i) => (
              <div key={i}>
                {msg.type === "question" ? (
                  /* User bubble — right-aligned */
                  <div className="flex flex-col items-end gap-1">
                    <div
                      className="px-4 py-3 rounded-xl text-sm leading-relaxed text-white max-w-xl shadow-sm"
                      style={{ background: C.primary }}
                    >
                      {msg.text}
                    </div>
                  </div>
                ) : (
                  /* AI answer — left-aligned with avatar */
                  <div className="flex flex-col gap-2 max-w-2xl">
                    {/* Avatar row */}
                    <div className="flex items-center gap-2">
                      <div
                        className="w-6 h-6 rounded flex items-center justify-center text-white shrink-0"
                        style={{ background: C.primary }}
                      >
                        <span className="material-symbols-outlined" style={{ fontSize: "14px", fontVariationSettings: "'FILL' 1" }}>
                          smart_toy
                        </span>
                      </div>
                      <span className="text-[11px] font-bold tracking-tight" style={{ color: C.primary }}>
                        DOCRAG INTELLIGENCE
                      </span>
                    </div>
                    {/* Bubble */}
                    <div
                      className="p-5 rounded-xl text-sm leading-relaxed border shadow-sm"
                      style={{ background: "#f2f4f6", borderColor: "rgba(226,232,240,0.5)", color: "#191c1e" }}
                    >
                      {msg.streaming && !msg.text ? (
                        /* Thinking phases — shown while waiting for first token */
                        <span className="flex items-center gap-3">
                          <span
                            className="material-symbols-outlined shrink-0 animate-spin"
                            style={{ fontSize: "16px", color: C.primary, animationDuration: "1.2s" }}
                          >
                            {THINKING_PHASES[thinkingPhase].icon}
                          </span>
                          <span
                            key={thinkingPhase}
                            className="text-xs font-medium"
                            style={{ color: C.primary, animation: "fadeIn 0.35s ease" }}
                          >
                            {THINKING_PHASES[thinkingPhase].label}
                            <span className="inline-flex gap-0.5 ml-1 align-middle">
                              {[0, 1, 2].map(i => (
                                <span
                                  key={i}
                                  className="w-1 h-1 rounded-full animate-bounce inline-block"
                                  style={{ background: C.primary, animationDelay: `${i * 0.18}s` }}
                                />
                              ))}
                            </span>
                          </span>
                        </span>
                      ) : (
                        <>
                          {msg.text || (msg.streaming ? "" : "—")}
                          {msg.streaming && (
                            <span
                              className="inline-block w-0.5 h-3.5 ml-0.5 align-middle animate-pulse"
                              style={{ background: C.primary }}
                            />
                          )}
                        </>
                      )}
                    </div>
                    {/* Inline citation pills */}
                    {msg.sources?.length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-1">
                        {msg.sources.map((src, j) => (
                          <button
                            key={j}
                            onClick={() => handlePillClick(src)}
                            className="inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-full border font-semibold cursor-pointer transition-all hover:opacity-80 hover:shadow-sm active:scale-[0.97]"
                            style={{ background: "#eef2ff", color: C.primary, borderColor: "#c5d4fe" }}
                            title="View source page"
                          >
                            <span className="material-symbols-outlined" style={{ fontSize: "12px", fontVariationSettings: "'FILL' 1" }}>
                              description
                            </span>
                            {src.doc_name} · p.{src.page} §{src.passage_index}
                          </button>
                        ))}
                      </div>
                    )}
                    {/* Not found */}
                    {!msg.found && (
                      <p className="text-[11px] flex items-center gap-1" style={{ color: "#94a3b8" }}>
                        <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>info</span>
                        Could not locate an answer in the uploaded documents
                      </p>
                    )}
                  </div>
                )}
              </div>
            ))}


            <div ref={bottomRef} />
          </div>
        </div>

        {/* ── Input area ── */}
        <div className="px-8 py-6" style={{ background: "#f7f9fb", borderTop: "1px solid rgba(226,232,240,0.6)" }}>
          {!isReady && (
            <p className="text-[11px] mb-3 text-center" style={{ color: "#94a3b8" }}>
              Upload and index at least one document to enable chat
            </p>
          )}
          <div className="max-w-3xl mx-auto">
            <div
              className="bg-white rounded-xl shadow-sm border p-4 transition-all"
              style={{ borderColor: "rgba(226,232,240,0.8)" }}
            >
              <textarea
                value={question}
                onChange={e => setQuestion(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  isReady
                    ? "Ask a question about your documents… (Enter to send, Shift+Enter for new line)"
                    : "Upload and index a document to start asking questions…"
                }
                disabled={!isReady}
                rows={2}
                className="w-full bg-transparent border-none resize-none outline-none text-sm leading-relaxed disabled:opacity-50 disabled:cursor-not-allowed"
                style={{ color: "#191c1e" }}
              />
              <div className="flex items-center justify-between mt-3 pt-3" style={{ borderTop: "1px solid #f1f5f9" }}>
                <div />
                <button
                  onClick={handleSubmit}
                  disabled={!question.trim() || loading || !isReady}
                  className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-bold text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90 active:scale-[0.97]"
                  style={{ background: `linear-gradient(135deg, ${C.primary} 0%, ${C.primary2} 100%)` }}
                >
                  Analyze
                  <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>send</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Snippet modal (portal → document.body so z-index is unaffected by parent stacking contexts) ── */}
      {snippetModal && createPortal(
        <div
          className="fixed inset-0 flex items-center justify-center p-4"
          style={{ background: "rgba(0,0,0,0.55)", zIndex: 9999 }}
          onClick={handleModalClose}
        >
          <div
            className="flex flex-col rounded-2xl shadow-2xl overflow-hidden"
            style={{ background: "white", width: "100%", maxWidth: "780px", maxHeight: "90vh" }}
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div
              className="flex items-center justify-between px-6 py-4 shrink-0"
              style={{ borderBottom: "1px solid #e2e8f0" }}
            >
              <div className="flex flex-col gap-0.5 min-w-0">
                <span className="font-bold text-sm truncate" style={{ color: C.primary }}>
                  {snippetModal.src.doc_name}
                </span>
                <span className="text-[11px]" style={{ color: "#94a3b8" }}>
                  Page {snippetModal.src.page} · Passage {snippetModal.src.passage_index}
                </span>
              </div>
              <div className="flex items-center gap-2 shrink-0 ml-4">
                <button
                  onClick={handleCopyImage}
                  disabled={!snippetModal.imageUrl}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90"
                  style={{ background: copySuccess ? "#16a34a" : `linear-gradient(135deg, ${C.primary} 0%, ${C.primary2} 100%)` }}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>
                    {copySuccess ? "check" : "content_copy"}
                  </span>
                  {copySuccess ? "Copied!" : "Copy Image"}
                </button>
                <button
                  onClick={handleModalClose}
                  className="flex items-center justify-center w-8 h-8 rounded-lg transition-all hover:bg-slate-100"
                  style={{ color: "#64748b" }}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: "20px" }}>close</span>
                </button>
              </div>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto custom-scrollbar flex items-center justify-center" style={{ minHeight: 0 }}>
              {snippetModal.loading && (
                <div className="flex flex-col items-center gap-3 py-16">
                  <div
                    className="w-10 h-10 rounded-full border-4 border-t-transparent animate-spin"
                    style={{ borderColor: `${C.primary} transparent ${C.primary} ${C.primary}` }}
                  />
                  <span className="text-sm" style={{ color: "#94a3b8" }}>Rendering page…</span>
                </div>
              )}

              {!snippetModal.loading && snippetModal.error === "docx" && (
                <div className="p-8 w-full">
                  <div
                    className="rounded-xl p-6 border-l-4"
                    style={{ background: "#f8fafc", borderLeftColor: C.primary }}
                  >
                    <p className="text-xs font-bold uppercase tracking-wider mb-3" style={{ color: C.primary }}>
                      Cited Passage
                    </p>
                    <p className="text-sm leading-relaxed" style={{ color: "#191c1e" }}>
                      "{snippetModal.src.text}"
                    </p>
                    <p className="text-[11px] mt-4" style={{ color: "#94a3b8" }}>
                      Page rendering is only available for PDF documents.
                    </p>
                  </div>
                </div>
              )}

              {!snippetModal.loading && snippetModal.error && snippetModal.error !== "docx" && (
                <div className="flex flex-col items-center gap-2 py-16">
                  <span className="material-symbols-outlined" style={{ fontSize: "32px", color: "#f87171" }}>error</span>
                  <p className="text-sm" style={{ color: "#64748b" }}>{snippetModal.error}</p>
                </div>
              )}

              {!snippetModal.loading && snippetModal.imageUrl && (
                <img
                  src={snippetModal.imageUrl}
                  alt={`Page ${snippetModal.src.page} of ${snippetModal.src.doc_name}`}
                  className="w-full h-auto block"
                />
              )}
            </div>

            {/* Footer — passage text */}
            {snippetModal.src.text && (
              <div
                className="px-6 py-4 shrink-0 text-xs leading-relaxed"
                style={{
                  borderTop: "1px solid #e2e8f0",
                  color: "#64748b",
                  display: "-webkit-box",
                  WebkitLineClamp: 4,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                }}
              >
                <span className="font-semibold" style={{ color: C.primary }}>Cited: </span>
                "{snippetModal.src.text}"
              </div>
            )}
          </div>
        </div>,
        document.body
      )}

    </div>
  )
}
