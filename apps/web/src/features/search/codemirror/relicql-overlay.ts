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

import { parser as relicOverlayParser } from "@/features/search/codemirror/relicql.parser"

const relicSpanHighlight = HighlightStyle.define([
  { tag: tags.function(tags.variableName), class: "cm-relicAttrCall" },
  { tag: tags.function(tags.typeName), class: "cm-relicRelationCall" },
])

const relicBuiltinMark = Decoration.mark({ class: "cm-relicBuiltin" })
const relicArgStringMark = Decoration.mark({ class: "cm-relicArgString" })

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
    decoration: relicBuiltinMark,
  })

  const pathStart = base + match[0].indexOf(match[4])
  entries.push({
    from: pathStart,
    to: pathStart + match[4].length,
    decoration: relicArgStringMark,
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
    decoration: relicBuiltinMark,
  })

  const typeStart = base + match[0].indexOf(match[4])
  entries.push({
    from: typeStart,
    to: typeStart + match[4].length,
    decoration: relicArgStringMark,
  })

  if (match[5]) {
    const directionStart = base + match[0].lastIndexOf(match[5])
    entries.push({
      from: directionStart,
      to: directionStart + match[5].length,
      decoration: relicArgStringMark,
    })
  }
}

function buildRelicDecorations(view: EditorView): DecorationSet {
  const entries: DecorationEntry[] = []
  const docText = view.state.doc.toString()
  if (!docText) {
    return Decoration.none
  }

  const tree = relicOverlayParser.parse(docText)

  highlightTree(tree, relicSpanHighlight, (from, to, classes) => {
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
      if (node.name === "RelicAttr") {
        addAttrDecorations(entries, node.from, text)
        return
      }

      if (node.name === "RelicRelation") {
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

class RelicOverlayView {
  decorations: DecorationSet

  constructor(view: EditorView) {
    this.decorations = buildRelicDecorations(view)
  }

  update(update: ViewUpdate) {
    if (update.docChanged) {
      this.decorations = buildRelicDecorations(update.view)
    }
  }
}

export const relicqlOverlayExtension = ViewPlugin.fromClass(RelicOverlayView, {
  decorations: (plugin) => plugin.decorations,
})
