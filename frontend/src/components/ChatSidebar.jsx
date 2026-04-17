// Design tokens
const C = {
  primary:   "#003371",
  primary2:  "#00499c",
  surface:   "#f8fafc",
  text:      "#0f172a",
  muted:     "#64748b",
  faint:     "#94a3b8",
  hover:     "#f1f5f9",
  active:    "#dbeafe",
  border:    "#e2e8f0",
}

export default function ChatSidebar({
  sessions = [],
  documents = [],
  activeView,
  activeSessionId,
  onSelectSession,
  onNew,
  onNavigate,
}) {
  const total   = documents.length
  const indexed = documents.filter(d => d.status === "indexed").length
  const processing = documents.some(d => d.status === "processing" || d.status === "pending")
  const hasFailed  = documents.some(d => d.status === "failed")

  const dot = processing
    ? { color: "#F59E0B", label: "Processing" }
    : indexed > 0
    ? { color: "#16A34A", label: "Ready" }
    : hasFailed
    ? { color: "#DC2626", label: "Error" }
    : { color: C.faint,   label: "Idle" }

  return (
    <aside
      className="h-screen w-64 flex flex-col fixed left-0 top-0 z-50 py-6 px-4"
      style={{ background: C.surface, borderRight: `1px solid ${C.border}` }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 mb-8 px-2">
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center text-white shrink-0"
          style={{ background: C.primary }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: "18px", fontVariationSettings: "'FILL' 1" }}>
            dataset
          </span>
        </div>
        <div>
          <h1 className="text-base font-extrabold tracking-tight leading-tight" style={{ color: C.primary }}>DocRAG</h1>
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em]" style={{ color: C.faint }}>
            Informed Intelligence
          </p>
        </div>
      </div>

      {/* New Chat */}
      <button
        onClick={onNew}
        className="mb-6 w-full py-3 px-4 rounded-lg text-white flex items-center justify-center gap-2 text-sm font-semibold transition-all hover:opacity-90 active:scale-[0.98]"
        style={{
          background: `linear-gradient(135deg, ${C.primary} 0%, ${C.primary2} 100%)`,
          boxShadow: "0 4px 14px rgba(0,51,113,0.18)",
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: "20px" }}>add_comment</span>
        New Chat
      </button>

      {/* Nav */}
      <nav className="space-y-0.5">
        <NavItem icon="chat"         label="Research Chat" active={activeView === "chat"}   onClick={() => onNavigate("chat")} />
        <NavItem icon="cloud_upload" label="Upload"        active={activeView === "upload"} onClick={() => onNavigate("upload")}
          badge={total > 0 ? `${indexed}/${total}` : null}
        />
        <NavItem icon="settings"     label="Settings"      active={false} onClick={() => {}} />
      </nav>

      {/* Session history */}
      {sessions.length > 0 && (
        <div className="mt-6">
          <p
            className="text-[10px] font-bold uppercase tracking-[0.15em] mb-2 px-3"
            style={{ color: C.faint }}
          >
            Recent Sessions
          </p>
          <div className="space-y-0.5">
            {sessions.slice(0, 10).map(s => (
              <button
                key={s.id}
                onClick={() => onSelectSession(s.id)}
                className="w-full text-left px-3 py-2 rounded-lg text-xs truncate transition-colors"
                style={{
                  color:      activeSessionId === s.id ? C.primary : C.muted,
                  background: activeSessionId === s.id ? C.active  : "transparent",
                  fontWeight: activeSessionId === s.id ? 600 : 400,
                }}
                onMouseEnter={e => { if (activeSessionId !== s.id) e.currentTarget.style.background = C.hover }}
                onMouseLeave={e => { if (activeSessionId !== s.id) e.currentTarget.style.background = "transparent" }}
              >
                {s.title}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex-1" />

      {/* System state */}
      <div
        className="mb-4 px-3 py-2 rounded-lg flex items-center gap-2"
        style={{ background: "#f1f5f9" }}
      >
        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: dot.color }} />
        <p className="text-[11px] font-medium" style={{ color: C.muted }}>
          {dot.label}
          {indexed > 0 && !processing && (
            <span style={{ color: C.faint }}> · {indexed} doc{indexed > 1 ? "s" : ""}</span>
          )}
        </p>
      </div>

      {/* User */}
      <div
        className="pt-4 px-2 flex items-center gap-3"
        style={{ borderTop: `1px solid ${C.border}` }}
      >
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0"
          style={{ background: C.primary }}
        >
          R
        </div>
        <div className="overflow-hidden">
          <p className="text-xs font-bold truncate" style={{ color: C.text }}>Raahul</p>
          <p className="text-[10px]" style={{ color: C.faint }}>Local · Private</p>
        </div>
      </div>
    </aside>
  )
}

function NavItem({ icon, label, active, onClick, badge }) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all"
      style={{
        color:      active ? "#003371" : "#64748b",
        background: active ? "#dbeafe" : "transparent",
        fontWeight: active ? 600 : 500,
      }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.background = "#f1f5f9" }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.background = "transparent" }}
    >
      <span
        className="material-symbols-outlined shrink-0"
        style={{
          fontSize: "20px",
          color: active ? "#003371" : "#94a3b8",
          fontVariationSettings: active ? "'FILL' 1" : "'FILL' 0",
        }}
      >
        {icon}
      </span>
      <span className="flex-1 text-left">{label}</span>
      {badge && (
        <span
          className="text-[10px] px-1.5 py-0.5 rounded font-semibold shrink-0"
          style={{ background: active ? "#bfdbfe" : "#dbeafe", color: "#003371" }}
        >
          {badge}
        </span>
      )}
    </button>
  )
}
