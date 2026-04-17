const C = { primary: "#003371", primary2: "#00499c" }

const STATUS = {
  indexed:    { label: "Indexed",    dot: "#16a34a" },
  processing: { label: "Processing", dot: "#f59e0b" },
  pending:    { label: "Pending",    dot: "#f59e0b" },
  failed:     { label: "Failed",     dot: "#dc2626" },
}

export default function DocumentLibrary({ documents = [], onDelete }) {
  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{ background: "white", borderColor: "rgba(226,232,240,0.8)" }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-5 py-4"
        style={{ borderBottom: "1px solid rgba(226,232,240,0.6)" }}
      >
        <h3
          className="font-extrabold text-sm tracking-tight flex items-center gap-2"
          style={{ color: C.primary }}
        >
          <span
            className="material-symbols-outlined"
            style={{ fontSize: "18px", fontVariationSettings: "'FILL' 1" }}
          >
            folder_open
          </span>
          Document Library
        </h3>
        <span
          className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
          style={{ background: "#eef2ff", color: C.primary }}
        >
          {documents.length} file{documents.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Empty state */}
      {documents.length === 0 ? (
        <div className="py-12 flex flex-col items-center gap-3">
          <div
            className="w-12 h-12 rounded-full flex items-center justify-center"
            style={{ background: "#f1f5f9" }}
          >
            <span
              className="material-symbols-outlined"
              style={{ fontSize: "24px", color: "#94a3b8", fontVariationSettings: "'FILL' 1" }}
            >
              folder_open
            </span>
          </div>
          <p className="text-sm font-medium" style={{ color: "#94a3b8" }}>No documents yet</p>
          <p className="text-xs" style={{ color: "#cbd5e1" }}>Uploaded files will appear here</p>
        </div>
      ) : (
        <div className="divide-y" style={{ borderColor: "rgba(226,232,240,0.4)" }}>
          {documents.map(doc => {
            const s = STATUS[doc.status] ?? STATUS.pending
            const isPdf = doc.file_type === "pdf"
            return (
              <div
                key={doc.id}
                className="flex items-start gap-3 px-5 py-4 group transition-colors"
                style={{ background: "white" }}
                onMouseEnter={e => e.currentTarget.style.background = "#f8fafc"}
                onMouseLeave={e => e.currentTarget.style.background = "white"}
              >
                {/* File icon */}
                <div
                  className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0 mt-0.5"
                  style={{ background: "#f1f5f9" }}
                >
                  <span
                    className="material-symbols-outlined"
                    style={{
                      fontSize: "20px",
                      color: isPdf ? "#dc2626" : "#003371",
                      fontVariationSettings: "'FILL' 1",
                    }}
                  >
                    {isPdf ? "picture_as_pdf" : "description"}
                  </span>
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p
                    className="text-xs font-semibold truncate leading-snug"
                    style={{ color: "#191c1e" }}
                  >
                    {doc.original_name}
                  </p>
                  <p className="text-[11px] mt-0.5" style={{ color: "#94a3b8" }}>
                    {new Date(doc.created_at).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })}
                  </p>
                  {/* Status row */}
                  <div className="flex items-center gap-1.5 mt-1.5">
                    <span
                      className="w-1.5 h-1.5 rounded-full shrink-0"
                      style={{ background: s.dot }}
                    />
                    <span className="text-[11px] font-medium" style={{ color: s.dot }}>
                      {s.label}
                    </span>
                    {doc.page_count > 0 && (
                      <>
                        <span style={{ color: "#e2e8f0" }}>·</span>
                        <span className="text-[11px]" style={{ color: "#94a3b8" }}>
                          {doc.page_count}p
                        </span>
                      </>
                    )}
                  </div>
                </div>

                {/* Delete */}
                <button
                  onClick={() => onDelete(doc.id)}
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-md"
                  style={{ color: "#94a3b8" }}
                  onMouseEnter={e => { e.currentTarget.style.color = "#dc2626"; e.currentTarget.style.background = "#fee2e2" }}
                  onMouseLeave={e => { e.currentTarget.style.color = "#94a3b8"; e.currentTarget.style.background = "transparent" }}
                  title="Remove document"
                >
                  <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
                    delete
                  </span>
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
