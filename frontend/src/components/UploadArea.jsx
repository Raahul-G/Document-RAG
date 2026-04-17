import { useRef, useState } from "react"

export default function UploadArea({ onUploadComplete }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)

  const handleFiles = (files) => {
    const allowed = ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
    const valid = Array.from(files).filter((f) => allowed.includes(f.type))
    if (valid.length === 0) return
    console.log("Files to upload:", valid.map((f) => f.name))
    onUploadComplete?.()
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files) }}
      className="rounded-xl border border-dashed py-12 flex flex-col items-center gap-4 transition-colors"
      style={{
        borderColor: dragging ? "#003499" : "#C7D7F5",
        background: dragging ? "#EEF2FF" : "#FAFBFF",
      }}
    >
      {/* Icon */}
      <div className="w-14 h-14 rounded-2xl flex items-center justify-center" style={{ background: "#EEF2FF" }}>
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
          <path d="M12 16V8M12 8L9 11M12 8L15 11" stroke="#003499" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M20 16.5A4.5 4.5 0 0016 12H15a7 7 0 10-11.95 5" stroke="#003499" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      </div>

      {/* Text */}
      <div className="text-center">
        <p className="text-sm font-semibold" style={{ color: "#0D1B3E" }}>Upload knowledge assets</p>
        <p className="text-xs mt-1" style={{ color: "#6B7280" }}>
          Drag and drop PDF or DOCX files. Max size 50MB per document.
        </p>
      </div>

      {/* Button */}
      <button
        onClick={() => inputRef.current?.click()}
        className="px-5 py-2 rounded-lg text-sm font-medium border transition-colors"
        style={{ borderColor: "#003499", color: "#003499", background: "white" }}
        onMouseEnter={e => { e.currentTarget.style.background = "#EEF2FF" }}
        onMouseLeave={e => { e.currentTarget.style.background = "white" }}
      >
        Select Files
      </button>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,.docx"
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
    </div>
  )
}
