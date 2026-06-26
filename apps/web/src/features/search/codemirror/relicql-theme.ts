import { Prec } from "@codemirror/state"
import { EditorView } from "@codemirror/view"

export const relicqlEditorTheme = Prec.highest(
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
    backgroundColor: "var(--relic-selection-focused) !important",
  },
  ".cm-content:focus ::selection, .cm-line:focus ::selection": {
    backgroundColor: "var(--relic-selection-focused) !important",
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
  ".cm-relicKeyword": {
    color: "var(--relic-syntax-keyword)",
    fontWeight: "600",
  },
  ".cm-relicType": {
    color: "var(--relic-syntax-type)",
  },
  ".cm-relicSqlBuiltin": {
    color: "var(--relic-syntax-builtin)",
  },
  ".cm-relicNumber": {
    color: "var(--relic-syntax-number)",
  },
  ".cm-relicBool": {
    color: "var(--relic-syntax-bool)",
  },
  ".cm-relicNull": {
    color: "var(--relic-syntax-null)",
    fontStyle: "italic",
  },
  ".cm-relicString": {
    color: "var(--relic-syntax-string)",
  },
  ".cm-relicName": {
    color: "var(--relic-syntax-name)",
  },
  ".cm-relicOperator": {
    color: "var(--relic-syntax-operator)",
  },
  ".cm-relicPunctuation": {
    color: "var(--relic-syntax-punctuation)",
  },
  ".cm-relicComment": {
    color: "var(--relic-syntax-comment)",
    fontStyle: "italic",
  },
  ".cm-relicSpecial": {
    color: "var(--relic-syntax-special)",
  },
  ".cm-relicAttrCall": {
    borderRadius: "3px",
    backgroundColor:
      "color-mix(in oklab, var(--relic-syntax-attr) 18%, transparent)",
  },
  ".cm-relicRelationCall": {
    borderRadius: "3px",
    backgroundColor:
      "color-mix(in oklab, var(--relic-syntax-relation) 18%, transparent)",
  },
  ".cm-relicBuiltin": {
    color: "var(--relic-builtin)",
    fontWeight: "600",
  },
  ".cm-relicArgString": {
    color: "var(--relic-arg-string)",
  },
  })
)
