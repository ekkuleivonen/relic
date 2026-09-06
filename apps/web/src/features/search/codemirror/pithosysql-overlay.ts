import { HighlightStyle } from "@codemirror/language"
import { highlightTree, tags } from "@lezer/highlight"
import { RangeSetBuilder } from "@codemirror/state"
import {
  Decoration,
  EditorView,
  ViewPlugin,
  type DecorationSet,
  type ViewUpdate,
} from "@codemirror/view"

import { parser as pithosysOverlayParser } from "@/features/search/codemirror/pithosysql.parser"

const pithosysSpanHighlight = HighlightStyle.define([
  { tag: tags.function(tags.variableName), class: "cm-pithosysAttrCall" },
  { tag: tags.function(tags.typeName), class: "cm-pithosysRelationCall" },
])

const pithosysBuiltinMark = Decoration.mark({ class: "cm-pithosysBuiltin" })
const pithosysArgStringMark = Decoration.mark({ class: "cm-pithosysArgString" })

const attrPattern =
  /^(\s*)(attr)(\s*\(\s*)('(?:[^'\\]|\\.)*')(\s*\))/i
const relationPattern =
  /^(\s*)(has_relation)(\s*\(\s*)('(?:[^'\\]|\\.)*')(?:\s*,\s*('(?:[^'\\]|\\.)*'))?(\s*\))/i

type DecorationEntry = {
  from: number
  to: number
  decoration: Decoration
}

function addAttrDecorations(
  entries: DecorationEntry[],
  from: number,
  text: string
) {
  const match = attrPattern.exec(text)
  if (!match) {
    return
  }

  const base = from + (match.index ?? 0)
  const builtinStart = base + match[1].length
  entries.push({
    from: builtinStart,
    to: builtinStart + match[2].length,
    decoration: pithosysBuiltinMark,
  })

  const pathStart = base + match[0].indexOf(match[4])
  entries.push({
    from: pathStart,
    to: pathStart + match[4].length,
    decoration: pithosysArgStringMark,
  })
}

function addRelationDecorations(
  entries: DecorationEntry[],
  from: number,
  text: string
) {
  const match = relationPattern.exec(text)
  if (!match) {
    return
  }

  const base = from + (match.index ?? 0)
  const builtinStart = base + match[1].length
  entries.push({
    from: builtinStart,
    to: builtinStart + match[2].length,
    decoration: pithosysBuiltinMark,
  })

  const typeStart = base + match[0].indexOf(match[4])
  entries.push({
    from: typeStart,
    to: typeStart + match[4].length,
    decoration: pithosysArgStringMark,
  })

  if (match[5]) {
    const directionStart = base + match[0].lastIndexOf(match[5])
    entries.push({
      from: directionStart,
      to: directionStart + match[5].length,
      decoration: pithosysArgStringMark,
    })
  }
}

function buildPithosysDecorations(view: EditorView): DecorationSet {
  const entries: DecorationEntry[] = []
  const docText = view.state.doc.toString()
  if (!docText) {
    return Decoration.none
  }

  const tree = pithosysOverlayParser.parse(docText)

  highlightTree(tree, pithosysSpanHighlight, (from, to, classes) => {
    if (!classes) {
      return
    }

    entries.push({
      from,
      to,
      decoration: Decoration.mark({ class: classes }),
    })
  })

  tree.iterate({
    enter: (node) => {
      const text = view.state.doc.sliceString(node.from, node.to)
      if (node.name === "PithosysAttr") {
        addAttrDecorations(entries, node.from, text)
        return
      }

      if (node.name === "PithosysRelation") {
        addRelationDecorations(entries, node.from, text)
      }
    },
  })

  entries.sort((left, right) => left.from - right.from || left.to - right.to)

  const builder = new RangeSetBuilder<Decoration>()
  for (const entry of entries) {
    builder.add(entry.from, entry.to, entry.decoration)
  }

  return builder.finish()
}

class PithosysOverlayView {
  decorations: DecorationSet

  constructor(view: EditorView) {
    this.decorations = buildPithosysDecorations(view)
  }

  update(update: ViewUpdate) {
    if (update.docChanged) {
      this.decorations = buildPithosysDecorations(update.view)
    }
  }
}

export const pithosysqlOverlayExtension = ViewPlugin.fromClass(PithosysOverlayView, {
  decorations: (plugin) => plugin.decorations,
})
