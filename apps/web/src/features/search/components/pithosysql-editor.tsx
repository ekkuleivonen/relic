import { sql, PostgreSQL } from "@codemirror/lang-sql"
import { Compartment, Prec, type Extension } from "@codemirror/state"
import { EditorView, keymap } from "@codemirror/view"
import CodeMirror from "@uiw/react-codemirror"
import * as React from "react"

import { Kbd, KbdGroup } from "@/components/ui/kbd"
import {
  pithosysqlAutocompletion,
  setPithosysqlAttributeCatalog,
  setPithosysqlBucketNames,
  setPithosysqlRelationTypes,
} from "@/features/search/codemirror/pithosysql-completion"
import { pithosysqlOverlayExtension } from "@/features/search/codemirror/pithosysql-overlay"
import { pithosysqlSyntaxHighlighting } from "@/features/search/codemirror/pithosysql-syntax"
import { pithosysqlEditorTheme } from "@/features/search/codemirror/pithosysql-theme"
import type { SearchAttribute } from "@/types/search"

const pithosysqlLanguage = sql({
  dialect: PostgreSQL,
  upperCaseKeywords: true,
})

const submitKeymapCompartment = new Compartment()

const baseExtensions: Extension[] = [
  pithosysqlLanguage,
  pithosysqlSyntaxHighlighting,
  pithosysqlOverlayExtension,
  pithosysqlEditorTheme,
  pithosysqlAutocompletion,
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

type PithosysqlEditorProps = {
  value: string
  onChange: (value: string) => void
  attributes: SearchAttribute[]
  relationTypes?: string[]
  bucketNames?: string[]
  onSubmit?: () => void
}

export function PithosysqlEditor({
  value,
  onChange,
  attributes,
  relationTypes = [],
  bucketNames = [],
  onSubmit,
}: PithosysqlEditorProps) {
  const editorViewRef = React.useRef<EditorView | null>(null)
  const onSubmitRef = React.useRef(onSubmit)
  onSubmitRef.current = onSubmit

  React.useEffect(() => {
    setPithosysqlAttributeCatalog(attributes)
  }, [attributes])

  React.useEffect(() => {
    setPithosysqlRelationTypes(relationTypes)
  }, [relationTypes])

  React.useEffect(() => {
    setPithosysqlBucketNames(bucketNames)
  }, [bucketNames])

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
          setPithosysqlAttributeCatalog(attributes)
          setPithosysqlRelationTypes(relationTypes)
          setPithosysqlBucketNames(bucketNames)
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
