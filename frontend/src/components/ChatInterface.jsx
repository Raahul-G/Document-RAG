import { useEffect, useRef, useState } from "react"

const C = { primary: "#003371", primary2: "#00499c" }


export default function ChatInterface({ sessionId, isReady, onSessionCreated, onGoToUpload }) {
  const [question, setQuestion] = useState("")
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [currentSessionId, setCurrentSessionId] = useState(sessionId)
  const [activeSources, setActiveSources] = useState([])
  const bottomRef = useRef(null)

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
    try {
      const res = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, session_id: currentSessionId ?? null }),
      })
      if (res.status === 503) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail ?? "The AI service is temporarily unavailable.")
      }
      if (!res.ok) throw new Error(`Request failed (${res.status})`)
      const data = await res.json()
      if (!currentSessionId && data.session_id) {
        setCurrentSessionId(data.session_id)
        onSessionCreated?.()
      }
      const sources = data.sources ?? []
      if (sources.length > 0) setActiveSources(sources)
      setMessages(prev => [...prev, {
        type: "answer",
        text: data.found ? data.answer : "I could not find an answer to this question in the uploaded documents.",
        sources,
        found: data.found,
      }])
    } catch (err) {
      setMessages(prev => [...prev, {
        type: "answer",
        text: err.message || "Something went wrong. Please try again.",
        sources: [],
        found: false,
      }])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit() }
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
                      {msg.text}
                    </div>
                    {/* Inline citation pills */}
                    {msg.sources?.length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-1">
                        {msg.sources.map((src, j) => (
                          <span
                            key={j}
                            className="inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-full border font-semibold"
                            style={{ background: "#eef2ff", color: C.primary, borderColor: "#c5d4fe" }}
                          >
                            <span className="material-symbols-outlined" style={{ fontSize: "12px", fontVariationSettings: "'FILL' 1" }}>
                              description
                            </span>
                            {src.doc_name} · p.{src.page} §{src.passage_index}
                          </span>
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

            {/* Typing indicator */}
            {loading && (
              <div className="flex flex-col gap-2 max-w-2xl">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded flex items-center justify-center text-white shrink-0" style={{ background: C.primary }}>
                    <span className="material-symbols-outlined" style={{ fontSize: "14px", fontVariationSettings: "'FILL' 1" }}>smart_toy</span>
                  </div>
                  <span className="text-[11px] font-bold tracking-tight" style={{ color: C.primary }}>DOCRAG INTELLIGENCE</span>
                </div>
                <div
                  className="px-5 py-4 rounded-xl border shadow-sm flex items-center gap-2"
                  style={{ background: "#f2f4f6", borderColor: "rgba(226,232,240,0.5)" }}
                >
                  <span className="flex gap-1">
                    {[0, 1, 2].map(i => (
                      <span
                        key={i}
                        className="w-1.5 h-1.5 rounded-full animate-bounce"
                        style={{ background: C.primary, animationDelay: `${i * 0.15}s` }}
                      />
                    ))}
                  </span>
                  <span className="text-xs" style={{ color: "#94a3b8" }}>Analyzing documents...</span>
                </div>
              </div>
            )}

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
                <div className="flex items-center gap-1">
                  <button
                    className="p-1.5 rounded-lg transition-colors"
                    style={{ color: "#94a3b8" }}
                    onMouseEnter={e => e.currentTarget.style.color = C.primary}
                    onMouseLeave={e => e.currentTarget.style.color = "#94a3b8"}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: "20px" }}>attach_file</span>
                  </button>
                </div>
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

      {/* ── Citations right panel ── */}
      {activeSources.length > 0 && (
        <aside
          className="hidden lg:flex flex-col w-80 shrink-0 custom-scrollbar"
          style={{ background: "#f2f4f6", borderLeft: "1px solid rgba(226,232,240,0.5)" }}
        >
          {/* Panel header */}
          <div className="px-6 py-5" style={{ borderBottom: "1px solid rgba(226,232,240,0.5)" }}>
            <h3
              className="font-extrabold text-base tracking-tight flex items-center gap-2"
              style={{ color: C.primary }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: "20px" }}>auto_stories</span>
              Citations &amp; Sources
            </h3>
          </div>

          {/* Cards */}
          <div className="flex-1 overflow-y-auto custom-scrollbar px-6 py-5 space-y-5">
            {activeSources.map((src, i) => (
              <div key={i} className="group">
                <div className="flex items-center justify-between mb-2">
                  <span
                    className="inline-flex items-center justify-center w-5 h-5 rounded text-white text-[10px] font-bold"
                    style={{ background: C.primary }}
                  >
                    {i + 1}
                  </span>
                  <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: "#94a3b8" }}>
                    P.{src.page} §{src.passage_index}
                  </span>
                </div>
                <div
                  className="p-4 rounded-xl shadow-sm border-l-2 transition-all group-hover:shadow-md"
                  style={{ background: "white", borderLeftColor: C.primary }}
                >
                  <p className="text-xs font-semibold truncate mb-1.5" style={{ color: "#191c1e" }}>{src.doc_name}</p>
                  {src.section_title && (
                    <p className="text-[10px] mb-2 font-medium" style={{ color: "#94a3b8" }}>{src.section_title}</p>
                  )}
                  <p
                    className="text-xs leading-snug"
                    style={{
                      color: "#434652",
                      display: "-webkit-box",
                      WebkitLineClamp: 5,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                    }}
                  >
                    "{src.text}"
                  </p>
                </div>
              </div>
            ))}
          </div>

          {/* Reliability indicator */}
          <div
            className="px-6 py-5 mt-auto"
            style={{ borderTop: "1px solid rgba(226,232,240,0.5)", background: "#eceef0" }}
          >
            <div className="flex items-center justify-between text-[11px] mb-2">
              <span style={{ color: "#64748b" }}>Document-grounded</span>
              <span className="font-bold" style={{ color: C.primary }}>100%</span>
            </div>
            <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: "#c3c6d4" }}>
              <div className="w-full h-full rounded-full" style={{ background: C.primary }} />
            </div>
          </div>
        </aside>
      )}
    </div>
  )
}
