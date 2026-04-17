import { useState } from "react"

export default function ChatInterface({ sessionId }) {
  const [question, setQuestion] = useState("")
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!question.trim() || loading) return

    const q = question.trim()
    setQuestion("")
    setMessages((prev) => [...prev, { type: "question", text: q }])
    setLoading(true)

    // Query logic implemented in Milestone 5
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        { type: "answer", text: "Query pipeline not yet implemented.", sources: [], found: false },
      ])
      setLoading(false)
    }, 500)
  }

  return (
    <div className="flex flex-col h-full" style={{ background: "#F5F7FA" }}>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-8 py-6 space-y-5">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center gap-4 pb-16">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center" style={{ background: "#EEF2FF" }}>
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
                <circle cx="11" cy="11" r="7" stroke="#003499" strokeWidth="1.8" />
                <path d="M20 20L16.5 16.5" stroke="#003499" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
            </div>
            <div className="text-center">
              <p className="font-semibold text-sm" style={{ color: "#0D1B3E" }}>Ask your documents anything</p>
              <p className="text-xs mt-1 max-w-xs" style={{ color: "#9CA3AF" }}>
                Answers are sourced strictly from your uploaded documents. No internet access.
              </p>
            </div>
          </div>
        )}

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
                <div className="bg-white rounded-2xl rounded-bl-sm px-5 py-4 text-sm border border-gray-200 shadow-sm" style={{ color: "#374151" }}>
                  {msg.text}
                </div>
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
                {!msg.found && msg.type === "answer" && (
                  <p className="text-[11px] mt-1.5 flex items-center gap-1" style={{ color: "#9CA3AF" }}>
                    <span>ⓘ</span> Could not locate this in the uploaded documents
                  </p>
                )}
              </div>
            )}
          </div>
        ))}

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
      </div>

      {/* Input bar */}
      <div className="px-8 py-4 border-t border-gray-200 bg-white">
        <form onSubmit={handleSubmit} className="flex gap-3 items-center">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask a question about your documents..."
            className="flex-1 px-4 py-2.5 text-sm rounded-lg border outline-none transition-colors"
            style={{
              borderColor: "#E2E8F0",
              color: "#0D1B3E",
              background: "#F5F7FA",
            }}
            onFocus={e => e.currentTarget.style.borderColor = "#003499"}
            onBlur={e => e.currentTarget.style.borderColor = "#E2E8F0"}
          />
          <button
            type="submit"
            disabled={!question.trim() || loading}
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
  )
}
