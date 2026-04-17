const STATUS = {
  indexed:    { label: "INDEXED",    bg: "#EEF2FF", color: "#003499", border: "#C7D7F5" },
  processing: { label: "PROCESSING", bg: "#F3F4F6", color: "#6B7280", border: "#D1D5DB" },
  pending:    { label: "PENDING",    bg: "#FEFCE8", color: "#854D0E", border: "#FEF08A" },
  failed:     { label: "FAILED",     bg: "#FEF2F2", color: "#DC2626", border: "#FECACA" },
}

const FILE_ICON = {
  pdf: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="2" y="1" width="10" height="13" rx="1" stroke="#6B7280" strokeWidth="1.2" />
      <path d="M10 1v3h3" stroke="#6B7280" strokeWidth="1.2" strokeLinejoin="round" />
      <path d="M5 7h6M5 9.5h4" stroke="#6B7280" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  ),
  docx: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="2" y="1" width="10" height="13" rx="1" stroke="#6B7280" strokeWidth="1.2" />
      <path d="M10 1v3h3" stroke="#6B7280" strokeWidth="1.2" strokeLinejoin="round" />
      <path d="M5 7h6M5 9.5h6M5 12h4" stroke="#6B7280" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  ),
}

export default function DocumentLibrary({ documents = [], onDelete }) {
  return (
    <div>
      {/* Header row */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold tracking-widest uppercase" style={{ color: "#6B7280" }}>
            Inventory
          </span>
          <span className="text-xs font-semibold px-2 py-0.5 rounded-full" style={{ background: "#EEF2FF", color: "#003499" }}>
            {documents.length} Total
          </span>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {/* Column headers */}
        <div className="grid grid-cols-[1fr_120px_80px_110px_60px] px-4 py-2.5 border-b border-gray-100">
          {["File Name", "Added", "Size", "Status", ""].map((h) => (
            <span key={h} className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#9CA3AF" }}>
              {h}
            </span>
          ))}
        </div>

        {/* Rows */}
        {documents.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-sm" style={{ color: "#9CA3AF" }}>No documents uploaded yet.</p>
          </div>
        ) : (
          documents.map((doc, i) => {
            const s = STATUS[doc.status] ?? STATUS.pending
            const icon = FILE_ICON[doc.file_type] ?? FILE_ICON.pdf
            return (
              <div
                key={doc.id}
                className="grid grid-cols-[1fr_120px_80px_110px_60px] px-4 py-3 items-center transition-colors"
                style={{ borderTop: i > 0 ? "1px solid #F3F4F6" : "none", background: "white" }}
                onMouseEnter={e => e.currentTarget.style.background = "#FAFBFF"}
                onMouseLeave={e => e.currentTarget.style.background = "white"}
              >
                {/* Name */}
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-7 h-7 rounded-md flex items-center justify-center shrink-0" style={{ background: "#F5F7FA" }}>
                    {icon}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: "#0D1B3E" }}>{doc.original_name}</p>
                    <p className="text-[11px]" style={{ color: "#9CA3AF" }}>{doc.file_type.toUpperCase()} DOCUMENT</p>
                  </div>
                </div>

                {/* Added */}
                <span className="text-xs" style={{ color: "#6B7280" }}>
                  {new Date(doc.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                </span>

                {/* Size */}
                <span className="text-xs" style={{ color: "#6B7280" }}>—</span>

                {/* Status */}
                <span
                  className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold w-fit border"
                  style={{ background: s.bg, color: s.color, borderColor: s.border }}
                >
                  {s.label}
                </span>

                {/* Delete */}
                <button
                  onClick={() => onDelete(doc.id)}
                  className="text-xs transition-colors"
                  style={{ color: "#D1D5DB" }}
                  onMouseEnter={e => e.currentTarget.style.color = "#DC2626"}
                  onMouseLeave={e => e.currentTarget.style.color = "#D1D5DB"}
                >
                  Remove
                </button>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
