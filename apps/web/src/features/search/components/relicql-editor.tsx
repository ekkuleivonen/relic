import { sql, PostgreSQL } from "@codemirror/lang-sql"
import { Compartment, Prec, type Extension } from "@codemirror/state"
import { EditorView, keymap } from "@codemirror/view"
import CodeMirror from "@uiw/react-codemirror"
import * as React from "react"

import { Kbd, KbdGroup } from "@/components/ui/kbd"
import {
  relicqlAutocompletion,
  setRelicqlAttributeCatalog,
  setRelicqlRelationTypes,
} from "@/features/search/codemirror/relicql-completion"
import { relicqlOverlayExtension } from "@/features/search/codemirror/relicql-overlay"
import { relicqlSyntaxHighlighting } from "@/features/search/codemirror/relicql-syntax"
import { relicqlEditorTheme } from "@/features/search/codemirror/relicql-theme"
import type { SearchAttribute } from "@/types/search"

const relicqlLanguage = sql({
  dialect: PostgreSQL,
  upperCaseKeywords: true,
})

const submitKeymapCompartment = new Compartment()

const baseExtensions: Extension[] = [
  relicqlLanguage,
  relicqlSyntaxHighlighting,
  relicqlOverlayExtension,
  relicqlEditorTheme,
  relicqlAutocompletion,
  EditorView.lineWrapping,
]

function createSubmitKeymap(onSubmit: () => void): Extension {
  return Prec.highest(
    keymap.of([
      {
        key: "Shift-Enter",
        run: () => {
          onSubmit()
          return true
        },
      },
    ])
  )
}

type RelicqlEditorProps = {
  value: string
  onChange: (value: string) => void
  attributes: SearchAttribute[]
  relationTypes?: string[]
  onSubmit?: () => void
}

export function RelicqlEditor({
  value,
  onChange,
  attributes,
  relationTypes = [],
  onSubmit,
}: RelicqlEditorProps) {
  const editorViewRef = React.useRef<EditorView | null>(null)
  const onSubmitRef = React.useRef(onSubmit)
  onSubmitRef.current = onSubmit

  React.useEffect(() => {
    setRelicqlAttributeCatalog(attributes)
  }, [attributes])

  React.useEffect(() => {
    setRelicqlRelationTypes(relationTypes)
  }, [relationTypes])

  const extensions = React.useMemo(
    () => [
      ...baseExtensions,
      submitKeymapCompartment.of(createSubmitKeymap(() => onSubmitRef.current?.())),
    ],
    // Submit keymap is reconfigured below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  )

  React.useEffect(() => {
    const view = editorViewRef.current
    if (!view) {
      return
    }

    view.dispatch({
      effects: [
        submitKeymapCompartment.reconfigure(
          createSubmitKeymap(() => onSubmitRef.current?.())
        ),
      ],
    })
  }, [])

  return (
    <div className="relative overflow-hidden rounded-lg border">
      <CodeMirror
        value={value}
        height="220px"
        theme="none"
        extensions={extensions}
        onChange={onChange}
        onCreateEditor={(view) => {
          editorViewRef.current = view
          setRelicqlAttributeCatalog(attributes)
          setRelicqlRelationTypes(relationTypes)
        }}
        basicSetup={{
          lineNumbers: false,
          foldGutter: false,
          dropCursor: false,
          allowMultipleSelections: false,
          indentOnInput: true,
          bracketMatching: true,
          closeBrackets: false,
          autocompletion: false,
          highlightSelectionMatches: false,
          highlightActiveLine: false,
          highlightActiveLineGutter: false,
          syntaxHighlighting: false,
          highlightSpecialChars: false,
          drawSelection: false,
        }}
      />
      <div
        aria-label="Shift Enter to submit"
        className="pointer-events-none absolute right-2 bottom-2 flex items-center gap-1.5 rounded-md border border-border/60 bg-card/90 px-2 py-1 shadow-sm backdrop-blur-sm"
      >
        <KbdGroup>
          <Kbd>⇧</Kbd>
          <Kbd>+</Kbd>
          <Kbd>↵</Kbd>
        </KbdGroup>
      </div>
    </div>
  )
}
