import { useEffect, useRef, useState } from "react"

const SAMPLE_QUERIES = [
  "Summarize the key points",
  "What are the main findings?",
  "List all requirements mentioned",
  "What conclusions are drawn?",
]

export default function ChatInterface({ sessionId, isReady, onSessionCreated, onGoToUpload }) {
  const [question, setQuestion] = useState("")
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [currentSessionId, setCurrentSessionId] = useState(sessionId)
  const [activeSources, setActiveSources] = useState([])
  const bottomRef = useRef(null)

  // Load messages when session changes (sidebar selection or new chat)
  useEffect(() => {
    setCurrentSessionId(sessionId)
    if (!sessionId) {
      setMessages([])
      setActiveSources([])
      return
    }
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

  // Auto-scroll to bottom on new messages
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

      if (!res.ok) throw new Error(`HTTP ${res.status}`)
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
    } catch {
      setMessages(prev => [...prev, {
        type: "answer",
        text: "Something went wrong. Please check your connection and try again.",
        sources: [],
        found: false,
      }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex h-full" style={{ background: "#F5F7FA" }}>

      {/* ── Main chat column ── */}
      <div className="flex flex-col flex-1 min-w-0">

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-8 py-6 space-y-5">

          {/* Empty state */}
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center gap-5 pb-16">
              {!isReady ? (
                /* ── No documents indexed ── */
                <>
                  <div className="w-16 h-16 rounded-2xl flex items-center justify-center" style={{ background: "#EEF2FF" }}>
                    <svg width="30" height="30" viewBox="0 0 24 24" fill="none">
                      <path d="M9 13h6M12 10v6M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke="#003499" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>
                  <div className="text-center max-w-xs">
                    <p className="font-semibold text-sm" style={{ color: "#0D1B3E" }}>No documents indexed yet</p>
                    <p className="text-xs mt-2 leading-relaxed" style={{ color: "#9CA3AF" }}>
                      Upload a PDF or DOCX to get started. Answers are sourced strictly
                      from your documents — no internet access.
                    </p>
                    <p className="text-[11px] mt-3 font-medium" style={{ color: "#6B7280" }}>
                      Supported formats: PDF · DOCX
                    </p>
                  </div>
                  <button
                    onClick={onGoToUpload}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium text-white transition-colors"
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
                </>
              ) : (
                /* ── Ready — show sample queries ── */
                <>
                  <div className="w-14 h-14 rounded-2xl flex items-center justify-center" style={{ background: "#EEF2FF" }}>
                    <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
                      <circle cx="11" cy="11" r="7" stroke="#003499" strokeWidth="1.8" />
                      <path d="M20 20L16.5 16.5" stroke="#003499" strokeWidth="1.8" strokeLinecap="round" />
                    </svg>
                  </div>
                  <div className="text-center">
                    <p className="font-semibold text-sm" style={{ color: "#0D1B3E" }}>Ask your documents anything</p>
                    <p className="text-xs mt-1 max-w-xs" style={{ color: "#9CA3AF" }}>
                      Answers come strictly from your uploaded documents. No internet access.
                    </p>
                  </div>
                  {/* Sample query chips */}
                  <div className="flex flex-wrap gap-2 justify-center max-w-sm">
                    {SAMPLE_QUERIES.map((q) => (
                      <button
                        key={q}
                        onClick={() => setQuestion(q)}
                        className="px-3 py-1.5 rounded-full text-xs border transition-colors"
                        style={{ borderColor: "#C7D7F5", color: "#003499", background: "#EEF2FF" }}
                        onMouseEnter={e => e.currentTarget.style.background = "#DBEAFE"}
                        onMouseLeave={e => e.currentTarget.style.background = "#EEF2FF"}
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {/* Message bubbles */}
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.type === "question" ? "justify-end" : "justify-start"}`}>
              {msg.type === "question" ? (
                <div
                  className="max-w-xl rounded-2xl rounded-br-sm px-4 py-3 text-sm text-white"
                  style={{ background: "#003499" }}
                >
                  {msg.text}
                </div>
              ) : (
                <div className="max-w-2xl w-full">
                  <div
                    className="bg-white rounded-2xl rounded-bl-sm px-5 py-4 text-sm border border-gray-200 shadow-sm"
                    style={{ color: "#374151" }}
                  >
                    {msg.text}
                  </div>

                  {/* Inline citation pills */}
                  {msg.sources?.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {msg.sources.map((src, j) => (
                        <span
                          key={j}
                          className="inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-full border font-medium"
                          style={{ background: "#EEF2FF", color: "#003499", borderColor: "#C7D7F5" }}
                        >
                          <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
                            <rect x="1" y="1" width="7" height="9" rx="0.8" stroke="#003499" strokeWidth="1.2" />
                            <path d="M9 1.5v3h3" stroke="#003499" strokeWidth="1.2" />
                          </svg>
                          {src.doc_name} · p.{src.page} §{src.passage_index}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Not-found indicator */}
                  {!msg.found && msg.type === "answer" && (
                    <p className="text-[11px] mt-1.5 flex items-center gap-1" style={{ color: "#9CA3AF" }}>
                      <span>ⓘ</span> Could not locate an answer in the uploaded documents
                    </p>
                  )}
                </div>
              )}
            </div>
          ))}

          {/* Loading indicator */}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-5 py-3 flex items-center gap-2 shadow-sm">
                <span className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="w-1.5 h-1.5 rounded-full animate-bounce"
                      style={{ background: "#003499", animationDelay: `${i * 0.15}s` }}
                    />
                  ))}
                </span>
                <span className="text-xs" style={{ color: "#9CA3AF" }}>Searching documents...</span>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div className="px-8 py-4 border-t border-gray-200 bg-white">
          {!isReady && (
            <p className="text-[11px] mb-2 text-center" style={{ color: "#9CA3AF" }}>
              Upload and index at least one document to enable chat
            </p>
          )}
          <form onSubmit={handleSubmit} className="flex gap-3 items-center">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={
                isReady
                  ? "Ask a question about your documents..."
                  : "Waiting for indexed documents..."
              }
              disabled={!isReady}
              className="flex-1 px-4 py-2.5 text-sm rounded-lg border outline-none transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                borderColor: "#E2E8F0",
                color: "#0D1B3E",
                background: isReady ? "#F5F7FA" : "#F9FAFB",
              }}
              onFocus={e => { if (isReady) e.currentTarget.style.borderColor = "#003499" }}
              onBlur={e => e.currentTarget.style.borderColor = "#E2E8F0"}
            />
            <button
              type="submit"
              disabled={!question.trim() || loading || !isReady}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
              style={{ background: "#003499" }}
              onMouseEnter={e => { if (!e.currentTarget.disabled) e.currentTarget.style.background = "#002580" }}
              onMouseLeave={e => e.currentTarget.style.background = "#003499"}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M12 7H2M8 3L12 7L8 11" stroke="white" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Ask
            </button>
          </form>
        </div>
      </div>

      {/* ── Sources right panel (P2 — shown when last response has sources) ── */}
      {activeSources.length > 0 && (
        <div className="hidden lg:flex flex-col w-72 border-l border-gray-200 bg-white shrink-0">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
            <p className="text-[11px] font-semibold uppercase tracking-widest" style={{ color: "#6B7280" }}>
              Sources
            </p>
            <span
              className="text-[10px] font-semibold px-1.5 py-0.5 rounded"
              style={{ background: "#EEF2FF", color: "#003499" }}
            >
              {activeSources.length}
            </span>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {activeSources.map((src, i) => (
              <div
                key={i}
                className="rounded-xl border p-3 text-xs"
                style={{ background: "#FAFBFF", borderColor: "#E8EEFA" }}
              >
                <div className="flex items-center justify-between mb-1.5 gap-2">
                  <span className="font-semibold truncate" style={{ color: "#0D1B3E" }}>{src.doc_name}</span>
                  <span
                    className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium"
                    style={{ background: "#EEF2FF", color: "#003499" }}
                  >
                    p.{src.page} §{src.passage_index}
                  </span>
                </div>
                {src.section_title && (
                  <p className="text-[10px] mb-1.5 font-medium" style={{ color: "#9CA3AF" }}>
                    {src.section_title}
                  </p>
                )}
                <p className="leading-relaxed" style={{ color: "#6B7280", display: "-webkit-box", WebkitLineClamp: 5, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                  {src.text}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
