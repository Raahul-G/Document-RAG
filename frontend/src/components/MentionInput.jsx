/**
 * MentionInput — contenteditable input with @document tagging.
 *
 * Typing "@" opens a filtered dropdown of indexed documents.
 * Selecting a document inserts a non-editable chip inline.
 * Chips are stripped from the plain text emitted to the parent;
 * selected document IDs are reported separately via onChange.
 *
 * Props:
 *   documents  — full documents array from App state
 *   disabled   — bool
 *   placeholder — string
 *   onChange(text, tags) — called on every edit;
 *                          text = plain question without chip markup
 *                          tags = [{id, name}] for each chip present
 *   onSubmit() — called when Enter is pressed and dropdown is closed
 *
 * Ref methods (via forwardRef + useImperativeHandle):
 *   reset() — clears the contenteditable DOM and internal state
 */
import { forwardRef, useImperativeHandle, useRef, useState } from "react"

const PRIMARY = "#003371"

function stemName(filename) {
  return filename.replace(/\.[^.]+$/, "")
}

// ── Dropdown ──────────────────────────────────────────────────────────────────

function MentionDropdown({ options, highlighted, onSelect, onHighlight }) {
  return (
    <div
      style={{
        position: "absolute",
        bottom: "calc(100% + 8px)",
        left: 0,
        right: 0,
        zIndex: 50,
        background: "white",
        border: "1px solid #e2e8f0",
        borderRadius: "12px",
        boxShadow: "0 8px 28px rgba(0,0,0,0.13)",
        overflow: "hidden",
        maxHeight: "220px",
        overflowY: "auto",
      }}
      className="custom-scrollbar"
    >
      {/* Header label */}
      <div
        style={{
          padding: "6px 12px 5px",
          fontSize: "10px",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          color: "#94a3b8",
          borderBottom: "1px solid #f1f5f9",
          background: "#fafafa",
        }}
      >
        Scope to document
      </div>

      {options.map((doc, i) => {
        const stem = stemName(doc.original_name)
        const active = i === highlighted
        return (
          <button
            key={doc.id}
            type="button"
            // mousedown fires before blur — keeps the contenteditable focused
            onMouseDown={e => { e.preventDefault(); onSelect(doc) }}
            onMouseEnter={() => onHighlight(i)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              width: "100%",
              padding: "8px 12px",
              background: active ? "#eff6ff" : "transparent",
              border: "none",
              cursor: "pointer",
              textAlign: "left",
              color: active ? PRIMARY : "#191c1e",
              fontSize: "13px",
              transition: "background 0.1s",
            }}
          >
            <span
              className="material-symbols-outlined"
              style={{
                fontSize: "14px",
                color: PRIMARY,
                fontVariationSettings: "'FILL' 1",
                flexShrink: 0,
              }}
            >
              description
            </span>
            <span style={{ fontWeight: 700, color: PRIMARY, flexShrink: 0 }}>@</span>
            <span
              style={{
                flex: 1,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                fontWeight: active ? 600 : 400,
              }}
            >
              {stem}
            </span>
            <span
              style={{
                fontSize: "10px",
                color: "#94a3b8",
                background: "#f1f5f9",
                padding: "1px 5px",
                borderRadius: "4px",
                fontWeight: 600,
                flexShrink: 0,
              }}
            >
              {(doc.file_type ?? "").toUpperCase()}
            </span>
          </button>
        )
      })}
    </div>
  )
}

// ── MentionInput ──────────────────────────────────────────────────────────────

const MentionInput = forwardRef(function MentionInput(
  { documents, disabled, placeholder, onChange, onSubmit },
  ref
) {
  const editableRef = useRef(null)
  const [mentionQuery, setMentionQuery] = useState(null) // null = dropdown closed
  const [highlightedIdx, setHighlightedIdx] = useState(0)
  const [isEmpty, setIsEmpty] = useState(true)

  // Only indexed docs can be tagged
  const indexedDocs = (documents ?? []).filter(d => d.status === "indexed")

  const filteredOptions =
    mentionQuery === null
      ? []
      : indexedDocs.filter(d =>
          stemName(d.original_name).toLowerCase().startsWith(mentionQuery.toLowerCase())
        )

  const dropdownOpen = filteredOptions.length > 0

  // ── Imperative API ──────────────────────────────────────────────────────────

  useImperativeHandle(ref, () => ({
    reset() {
      if (!editableRef.current) return
      editableRef.current.innerHTML = ""
      setIsEmpty(true)
      setMentionQuery(null)
      setHighlightedIdx(0)
    },
  }))

  // ── DOM helpers ─────────────────────────────────────────────────────────────

  function readPlainText() {
    if (!editableRef.current) return ""
    let text = ""
    for (const node of editableRef.current.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) {
        text += node.textContent
      } else if (node.nodeName === "BR") {
        text += "\n"
      }
      // .mention-chip spans are skipped — they're the tags, not the question text
    }
    return text
  }

  function readTaggedDocs() {
    if (!editableRef.current) return []
    return Array.from(editableRef.current.querySelectorAll(".mention-chip")).map(chip => ({
      id: parseInt(chip.dataset.docId, 10),
      name: chip.dataset.docName,
    }))
  }

  function notifyChange() {
    onChange?.(readPlainText(), readTaggedDocs())
  }

  // Walk backward from caret to find an active @{query} fragment.
  // Returns the fragment (possibly "") or null if no active mention.
  function detectMentionContext() {
    const sel = window.getSelection()
    if (!sel?.rangeCount) return null
    const range = sel.getRangeAt(0)
    if (!range.collapsed) return null
    const container = range.startContainer
    if (container.nodeType !== Node.TEXT_NODE) return null
    const textBefore = container.textContent.slice(0, range.startOffset)
    const atIdx = textBefore.lastIndexOf("@")
    if (atIdx === -1) return null
    const fragment = textBefore.slice(atIdx + 1)
    // A space after @ means the mention was abandoned (user moved on)
    if (fragment.includes(" ")) return null
    return fragment
  }

  // Replace the typed @{query} with a chip DOM node and reposition the cursor.
  function commitMention(doc) {
    const sel = window.getSelection()
    if (!sel?.rangeCount) return
    const range = sel.getRangeAt(0)
    const textNode = range.startContainer
    if (textNode.nodeType !== Node.TEXT_NODE) return

    const caretOffset = range.startOffset
    // "@" + mentionQuery characters to remove
    const deleteCount = (mentionQuery?.length ?? 0) + 1
    const deleteStart = Math.max(0, caretOffset - deleteCount)

    // Delete the "@{query}" text
    const deleteRange = document.createRange()
    deleteRange.setStart(textNode, deleteStart)
    deleteRange.setEnd(textNode, caretOffset)
    deleteRange.deleteContents()

    // Build the chip element
    const stem = stemName(doc.original_name)
    const chip = document.createElement("span")
    chip.contentEditable = "false"
    chip.className = "mention-chip"
    chip.dataset.docId = String(doc.id)
    chip.dataset.docName = stem

    const label = document.createElement("span")
    label.textContent = "@" + stem

    const xBtn = document.createElement("button")
    xBtn.type = "button"
    xBtn.className = "mention-chip-x"
    xBtn.textContent = "×"
    xBtn.setAttribute("aria-label", `Remove ${stem}`)

    chip.appendChild(label)
    chip.appendChild(xBtn)

    // Insert chip at the (now-collapsed) cursor position
    deleteRange.insertNode(chip)

    // Insert a regular space after the chip so the cursor lands outside it
    const space = document.createTextNode(" ")
    chip.after(space)

    // Move cursor after the space
    const newRange = document.createRange()
    newRange.setStartAfter(space)
    newRange.collapse(true)
    sel.removeAllRanges()
    sel.addRange(newRange)

    setMentionQuery(null)
    setHighlightedIdx(0)
    setIsEmpty(false)
    notifyChange()
    editableRef.current?.focus()
  }

  // ── Event handlers ──────────────────────────────────────────────────────────

  const handleInput = () => {
    const el = editableRef.current
    if (!el) return

    // Clear stray <br> left by browser when content is deleted
    const hasChips = !!el.querySelector(".mention-chip")
    const hasText = el.textContent.trim() !== ""
    if (!hasText && !hasChips) {
      el.innerHTML = ""
      setIsEmpty(true)
    } else {
      setIsEmpty(false)
    }

    // Update mention context
    const q = detectMentionContext()
    setMentionQuery(q)
    if (q !== null) setHighlightedIdx(0)

    notifyChange()
  }

  const handleKeyDown = (e) => {
    // Dropdown keyboard navigation takes priority
    if (dropdownOpen) {
      if (e.key === "ArrowDown") {
        e.preventDefault()
        setHighlightedIdx(i => Math.min(i + 1, filteredOptions.length - 1))
        return
      }
      if (e.key === "ArrowUp") {
        e.preventDefault()
        setHighlightedIdx(i => Math.max(i - 1, 0))
        return
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault()
        commitMention(filteredOptions[highlightedIdx])
        return
      }
      if (e.key === "Escape") {
        e.preventDefault()
        setMentionQuery(null)
        return
      }
    }
    // Enter without Shift → submit (when no dropdown is open)
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      onSubmit?.()
    }
  }

  const handlePaste = (e) => {
    e.preventDefault()
    const text = e.clipboardData.getData("text/plain")
    // execCommand triggers the input event which calls notifyChange
    if (!document.execCommand("insertText", false, text)) {
      // Fallback for browsers where execCommand is fully removed
      const sel = window.getSelection()
      if (sel?.rangeCount) {
        const range = sel.getRangeAt(0)
        range.deleteContents()
        const tn = document.createTextNode(text)
        range.insertNode(tn)
        range.setStartAfter(tn)
        range.collapse(true)
        sel.removeAllRanges()
        sel.addRange(range)
        handleInput()
      }
    }
  }

  // Event delegation: handle chip × button clicks
  const handleClick = (e) => {
    const xBtn = e.target.closest(".mention-chip-x")
    if (!xBtn) return
    e.preventDefault()
    const chip = xBtn.closest(".mention-chip")
    if (!chip) return
    // Remove the trailing space node too
    const next = chip.nextSibling
    if (next?.nodeType === Node.TEXT_NODE && next.textContent === " ") {
      next.remove()
    }
    chip.remove()
    const el = editableRef.current
    if (el) {
      const hasChips = !!el.querySelector(".mention-chip")
      const hasText = el.textContent.trim() !== ""
      if (!hasText && !hasChips) {
        el.innerHTML = ""
        setIsEmpty(true)
      }
    }
    notifyChange()
    editableRef.current?.focus()
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div style={{ position: "relative", width: "100%" }}>

      {/* Dropdown anchored above the input wrapper */}
      {dropdownOpen && (
        <MentionDropdown
          options={filteredOptions}
          highlighted={highlightedIdx}
          onSelect={commitMention}
          onHighlight={setHighlightedIdx}
        />
      )}

      {/* Editable area */}
      <div style={{ position: "relative" }}>

        {/* Placeholder — rendered as an overlay when content is empty */}
        {isEmpty && (
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              pointerEvents: "none",
              color: "#94a3b8",
              fontSize: "0.875rem",
              lineHeight: "1.625",
              userSelect: "none",
            }}
          >
            {placeholder}
          </div>
        )}

        <div
          ref={editableRef}
          contentEditable={!disabled}
          suppressContentEditableWarning
          onInput={handleInput}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          onClick={handleClick}
          role="textbox"
          aria-multiline="true"
          aria-label="Question input"
          style={{
            width: "100%",
            minHeight: "2.5rem",
            maxHeight: "8rem",
            overflowY: "auto",
            outline: "none",
            fontSize: "0.875rem",
            lineHeight: "1.625",
            color: "#191c1e",
            opacity: disabled ? 0.5 : 1,
            pointerEvents: disabled ? "none" : "auto",
            wordBreak: "break-word",
          }}
          className="custom-scrollbar"
        />
      </div>
    </div>
  )
})

export default MentionInput
