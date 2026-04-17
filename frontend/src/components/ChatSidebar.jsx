export default function ChatSidebar({
  sessions = [],
  documents = [],
  activeView,
  activeSessionId,
  onSelectSession,
  onNew,
  onNavigate,
}) {
  const total = documents.length
  const indexed = documents.filter(d => d.status === "indexed").length
  const processing = documents.some(d => d.status === "processing" || d.status === "pending")
  const hasFailed = documents.some(d => d.status === "failed")

  // System state dot
  const statusDot = processing
    ? { color: "#F59E0B", label: "Processing" }
    : indexed > 0
    ? { color: "#16A34A", label: "Ready" }
    : hasFailed
    ? { color: "#DC2626", label: "Error" }
    : { color: "#9CA3AF", label: "Idle" }

  return (
    <div className="w-56 flex flex-col bg-white border-r border-gray-200 shrink-0">

      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-gray-100">
        <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0" style={{ background: "#0D1B3E" }}>
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M9 2L11.5 7H16.5L12.5 10.5L14 15.5L9 12.5L4 15.5L5.5 10.5L1.5 7H6.5L9 2Z" fill="white" />
          </svg>
        </div>
        <div>
          <p className="text-sm font-semibold leading-tight" style={{ color: "#0D1B3E" }}>DocRAG</p>
          <p className="text-[10px] tracking-widest uppercase" style={{ color: "#9CA3AF" }}>Doc RAG System</p>
        </div>
      </div>

      {/* New Session button */}
      <div className="px-3 pt-4 pb-2">
        <button
          onClick={onNew}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium text-white transition-colors"
          style={{ background: "#003499" }}
          onMouseEnter={e => e.currentTarget.style.background = "#002580"}
          onMouseLeave={e => e.currentTarget.style.background = "#003499"}
        >
          <span className="text-base leading-none">+</span>
          New Session
        </button>
      </div>

      {/* Nav items */}
      <nav className="px-2 py-1">
        <NavItem
          label="Research Chat"
          active={activeView === "chat"}
          onClick={() => onNavigate("chat")}
          icon={
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M2 3h12v8H9l-3 3v-3H2V3z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
            </svg>
          }
        />
        <NavItem
          label="Documents"
          active={activeView === "upload"}
          onClick={() => onNavigate("upload")}
          badge={total > 0 ? `${indexed}/${total}` : null}
          icon={
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 2h7l3 3v9H3V2z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
              <path d="M10 2v3h3" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
            </svg>
          }
        />
      </nav>

      {/* Session history */}
      {sessions.length > 0 && (
        <div className="px-3 pt-3">
          <p className="text-[10px] font-semibold uppercase tracking-widest mb-1.5" style={{ color: "#9CA3AF" }}>
            Recent Sessions
          </p>
          <div className="space-y-0.5">
            {sessions.map((s) => (
              <button
                key={s.id}
                onClick={() => onSelectSession(s.id)}
                className="w-full text-left px-2 py-1.5 rounded text-xs truncate transition-colors"
                style={{
                  color: activeSessionId === s.id ? "#003499" : "#6B7280",
                  background: activeSessionId === s.id ? "#EEF2FF" : "transparent",
                  fontWeight: activeSessionId === s.id ? 500 : 400,
                }}
                onMouseEnter={e => { if (activeSessionId !== s.id) e.currentTarget.style.background = "#F5F7FA" }}
                onMouseLeave={e => { if (activeSessionId !== s.id) e.currentTarget.style.background = "transparent" }}
              >
                {s.title}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex-1" />

      {/* System state indicator */}
      <div className="mx-3 mb-2 px-3 py-2 rounded-lg flex items-center gap-2" style={{ background: "#F5F7FA" }}>
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ background: statusDot.color, boxShadow: `0 0 0 2px ${statusDot.color}33` }}
        />
        <p className="text-[11px] font-medium" style={{ color: "#6B7280" }}>
          {statusDot.label}
          {indexed > 0 && !processing && (
            <span style={{ color: "#9CA3AF" }}> · {indexed} doc{indexed > 1 ? "s" : ""}</span>
          )}
        </p>
      </div>

      {/* Bottom nav */}
      <div className="border-t border-gray-100 px-2 py-2 space-y-0.5">
        <NavItem label="Settings" icon={
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="2.5" stroke="currentColor" strokeWidth="1.4" />
            <path d="M8 1v2M8 13v2M1 8h2M13 8h2M2.93 2.93l1.41 1.41M11.66 11.66l1.41 1.41M2.93 13.07l1.41-1.41M11.66 4.34l1.41-1.41" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
          </svg>
        } />
      </div>

      {/* User */}
      <div className="px-3 py-3 border-t border-gray-100 flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0" style={{ background: "#003499" }}>
          R
        </div>
        <div className="min-w-0">
          <p className="text-xs font-medium truncate" style={{ color: "#0D1B3E" }}>Raahul</p>
          <p className="text-[10px]" style={{ color: "#9CA3AF" }}>Local · Private</p>
        </div>
      </div>
    </div>
  )
}

function NavItem({ label, active, onClick, icon, badge }) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors relative"
      style={{
        color: active ? "#003499" : "#6B7280",
        background: active ? "#EEF2FF" : "transparent",
        fontWeight: active ? 600 : 400,
      }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.background = "#F5F7FA" }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.background = "transparent" }}
    >
      {active && (
        <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r" style={{ background: "#003499" }} />
      )}
      <span style={{ color: active ? "#003499" : "#9CA3AF" }}>{icon}</span>
      <span className="flex-1 text-left">{label}</span>
      {badge && (
        <span
          className="text-[10px] px-1.5 py-0.5 rounded font-semibold shrink-0"
          style={{ background: active ? "#C7D7F5" : "#EEF2FF", color: "#003499" }}
        >
          {badge}
        </span>
      )}
    </button>
  )
}
