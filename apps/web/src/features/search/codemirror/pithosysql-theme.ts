import { Prec } from "@codemirror/state"
import { EditorView } from "@codemirror/view"

export const pithosysqlEditorTheme = Prec.highest(
  EditorView.theme({
  "&": {
    backgroundColor: "var(--card)",
    color: "var(--card-foreground)",
    fontSize: "13px",
  },
  "&.cm-focused": {
    outline: "none",
  },
  ".cm-scroller": {
    fontFamily:
      "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    lineHeight: "1.6",
    backgroundColor: "var(--card)",
  },
  ".cm-content": {
    backgroundColor: "var(--card)",
    color: "var(--card-foreground)",
    caretColor: "var(--foreground)",
    padding: "8px 12px",
  },
  ".cm-cursor, .cm-dropCursor": {
    borderLeftColor: "var(--foreground)",
  },
  ".cm-content ::selection, .cm-line ::selection": {
    backgroundColor: "var(--pithosys-selection-focused) !important",
  },
  ".cm-content:focus ::selection, .cm-line:focus ::selection": {
    backgroundColor: "var(--pithosys-selection-focused) !important",
  },
  ".cm-panels": {
    backgroundColor: "var(--popover)",
    color: "var(--popover-foreground)",
  },
  ".cm-tooltip": {
    backgroundColor: "var(--popover)",
    color: "var(--popover-foreground)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-md)",
  },
  ".cm-tooltip-autocomplete > ul > li": {
    padding: "4px 8px",
  },
  ".cm-tooltip-autocomplete > ul > li[aria-selected]": {
    backgroundColor: "var(--accent)",
    color: "var(--accent-foreground)",
  },
  ".cm-diagnostic-error": {
    borderBottom: "2px wavy var(--destructive)",
  },
  ".cm-lintRange-error": {
    backgroundImage: "none",
    borderBottom: "2px wavy var(--destructive)",
  },
  ".cm-pithosysKeyword": {
    color: "var(--pithosys-syntax-keyword)",
    fontWeight: "600",
  },
  ".cm-pithosysType": {
    color: "var(--pithosys-syntax-type)",
  },
  ".cm-pithosysSqlBuiltin": {
    color: "var(--pithosys-syntax-builtin)",
  },
  ".cm-pithosysNumber": {
    color: "var(--pithosys-syntax-number)",
  },
  ".cm-pithosysBool": {
    color: "var(--pithosys-syntax-bool)",
  },
  ".cm-pithosysNull": {
    color: "var(--pithosys-syntax-null)",
    fontStyle: "italic",
  },
  ".cm-pithosysString": {
    color: "var(--pithosys-syntax-string)",
  },
  ".cm-pithosysName": {
    color: "var(--pithosys-syntax-name)",
  },
  ".cm-pithosysOperator": {
    color: "var(--pithosys-syntax-operator)",
  },
  ".cm-pithosysPunctuation": {
    color: "var(--pithosys-syntax-punctuation)",
  },
  ".cm-pithosysComment": {
    color: "var(--pithosys-syntax-comment)",
    fontStyle: "italic",
  },
  ".cm-pithosysSpecial": {
    color: "var(--pithosys-syntax-special)",
  },
  ".cm-pithosysAttrCall": {
    borderRadius: "3px",
    backgroundColor:
      "color-mix(in oklab, var(--pithosys-syntax-attr) 18%, transparent)",
  },
  ".cm-pithosysRelationCall": {
    borderRadius: "3px",
    backgroundColor:
      "color-mix(in oklab, var(--pithosys-syntax-relation) 18%, transparent)",
  },
  ".cm-pithosysBuiltin": {
    color: "var(--pithosys-builtin)",
    fontWeight: "600",
  },
  ".cm-pithosysArgString": {
    color: "var(--pithosys-arg-string)",
  },
  })
)
