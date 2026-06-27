import {
  autocompletion,
  completionKeymap,
  completionStatus,
  startCompletion,
  type Completion,
  type CompletionContext,
  type CompletionResult,
} from "@codemirror/autocomplete"
import { EditorState, Prec, type Extension } from "@codemirror/state"
import { EditorView, keymap, type ViewUpdate } from "@codemirror/view"

import {
  BUILTIN_RELATION_TYPES,
  BUILTIN_SEARCH_ATTRIBUTES,
  RELATION_DIRECTIONS,
} from "@/features/search/constants"
import type { SearchAttribute } from "@/types/search"

const KEYWORD_COMPLETIONS: Completion[] = [
  "FROM",
  "WHERE",
  "AND",
  "OR",
  "NOT",
  "ORDER BY",
  "LIMIT",
  "OFFSET",
  "IN",
  "BETWEEN",
  "IS NULL",
  "IS NOT NULL",
  "LIKE",
  "ILIKE",
  "ASC",
  "DESC",
  "CAST",
  "AS",
  "timestamp",
  "date",
  "interval",
  "true",
  "false",
  "NULL",
].map((label) => ({
  label,
  type: "keyword",
}))

const FUNCTION_COMPLETIONS: Completion[] = [
  {
    label: "attr",
    type: "function",
    detail: "attribute reference",
    apply: "attr('')",
  },
  {
    label: "has_relation",
    type: "function",
    detail: "relation predicate",
    apply: "has_relation('')",
  },
  {
    label: "now()",
    type: "function",
    detail: "current timestamp",
    apply: "now()",
  },
]

const FIELD_COMPLETIONS: Completion[] = [
  "id",
  "bucket_id",
  "key",
  "created_at",
  "updated_at",
].map((label) => ({
  label,
  type: "variable",
  detail: "field",
}))

const SNIPPET_COMPLETIONS: Completion[] = [
  {
    label: "timestamp literal",
    type: "constant",
    apply: "timestamp ''",
  },
  {
    label: "date literal",
    type: "constant",
    apply: "date ''",
  },
  {
    label: "interval literal",
    type: "constant",
    apply: "interval '7 days'",
  },
  {
    label: "relative time",
    type: "constant",
    apply: "now() - interval '7 days'",
  },
]

const ATTR_CALL_PATTERN = /attr\s*\(\s*'/gi
const RELATION_CALL_PATTERN = /has_relation\s*\(\s*'/gi

let attributeCatalog: SearchAttribute[] = BUILTIN_SEARCH_ATTRIBUTES
let relationTypeCatalog: string[] = [...BUILTIN_RELATION_TYPES]

export function setRelicqlAttributeCatalog(attributes: SearchAttribute[]) {
  attributeCatalog =
    attributes.length > 0 ? attributes : BUILTIN_SEARCH_ATTRIBUTES
}

export function setRelicqlRelationTypes(relationTypes: string[]) {
  const merged = new Set<string>(BUILTIN_RELATION_TYPES)
  for (const relationType of relationTypes) {
    if (relationType.trim()) {
      merged.add(relationType)
    }
  }
  relationTypeCatalog = [...merged].sort((left, right) =>
    left.localeCompare(right)
  )
}

type QuotedArgContext = {
  from: number
  to: number
  prefix: string
}

type RelationCallContext = QuotedArgContext & {
  argument: "type" | "direction"
}

function quotedArgAt(
  text: string,
  pos: number,
  contentStart: number
): QuotedArgContext | null {
  let contentEnd = contentStart
  while (
    contentEnd < text.length &&
    text[contentEnd] !== "'" &&
    text[contentEnd] !== "\n"
  ) {
    contentEnd++
  }

  const hasClosingQuote = contentEnd < text.length && text[contentEnd] === "'"
  const maxPos = hasClosingQuote ? contentEnd : pos

  if (pos > maxPos) {
    const afterQuote = hasClosingQuote && pos === contentEnd + 1
    const beforeCloseParen =
      afterQuote && contentEnd + 1 < text.length && text[contentEnd + 1] === ")"
    if (!beforeCloseParen) {
      return null
    }

    const fullValue = text.slice(contentStart, contentEnd)
    if (!/^[\w.]*$/.test(fullValue)) {
      return null
    }

    return {
      from: contentStart,
      to: contentEnd,
      prefix: fullValue,
    }
  }

  const prefix = text.slice(contentStart, Math.min(pos, maxPos))
  if (!/^[\w.]*$/.test(prefix)) {
    return null
  }

  return {
    from: contentStart,
    to: Math.min(pos, maxPos),
    prefix,
  }
}

export function getAttrPathPrefixAt(state: EditorState, pos: number) {
  const text = state.doc.toString()
  let match: RegExpExecArray | null
  let active: QuotedArgContext | null = null

  while ((match = ATTR_CALL_PATTERN.exec(text)) !== null) {
    const pathStart = match.index + match[0].length
    if (pos < pathStart) {
      continue
    }

    const context = quotedArgAt(text, pos, pathStart)
    if (context) {
      active = context
    }
  }

  return active
}

export function getRelationCallContextAt(
  state: EditorState,
  pos: number
): RelationCallContext | null {
  const text = state.doc.toString()
  let match: RegExpExecArray | null
  let active: RelationCallContext | null = null

  while ((match = RELATION_CALL_PATTERN.exec(text)) !== null) {
    const typeStart = match.index + match[0].length
    if (pos < typeStart) {
      continue
    }

    const typeContext = quotedArgAt(text, pos, typeStart)
    if (typeContext) {
      active = {
        ...typeContext,
        argument: "type",
      }
      continue
    }

    let afterType = typeStart
    while (afterType < text.length && text[afterType] !== "'") {
      afterType++
    }
    if (afterType >= text.length || text[afterType] !== "'") {
      continue
    }
    afterType++

    const directionPrefix = text.slice(afterType).match(/^\s*,\s*'/)
    if (!directionPrefix) {
      continue
    }

    const directionStart = afterType + directionPrefix[0].length
    if (pos < directionStart) {
      continue
    }

    const directionContext = quotedArgAt(text, pos, directionStart)
    if (!directionContext) {
      continue
    }

    if (!/^[\w]*$/.test(directionContext.prefix)) {
      continue
    }

    active = {
      ...directionContext,
      argument: "direction",
    }
  }

  return active
}

type PathPrefixParts = {
  completedPath: string
  partialSegment: string
  replaceFrom: number
  replaceTo: number
}

export function splitAttrPathPrefix(
  pathStart: number,
  prefix: string,
  replaceTo: number
): PathPrefixParts {
  if (prefix.endsWith(".")) {
    const completedPath = prefix.slice(0, -1)
    const replaceFrom = pathStart + prefix.length
    return {
      completedPath,
      partialSegment: "",
      replaceFrom,
      replaceTo,
    }
  }

  const lastDot = prefix.lastIndexOf(".")
  if (lastDot === -1) {
    return {
      completedPath: "",
      partialSegment: prefix,
      replaceFrom: pathStart,
      replaceTo,
    }
  }

  return {
    completedPath: prefix.slice(0, lastDot),
    partialSegment: prefix.slice(lastDot + 1),
    replaceFrom: pathStart + lastDot + 1,
    replaceTo,
  }
}

type SegmentCompletion = {
  segment: string
  isLeaf: boolean
  type?: string
  fullPath: string
}

export function getNextSegmentCompletions(
  catalog: SearchAttribute[],
  completedPath: string,
  partialSegment: string
): SegmentCompletion[] {
  const depth = completedPath ? completedPath.split(".").length : 0
  const completedParts = completedPath ? completedPath.split(".") : []
  const normalizedPartial = partialSegment.toLowerCase()
  const seen = new Map<string, SegmentCompletion>()

  for (const attribute of catalog) {
    const segments = attribute.path.split(".")
    if (completedParts.some((part, index) => segments[index] !== part)) {
      continue
    }
    if (segments.length <= depth) {
      continue
    }

    const segment = segments[depth]!
    if (
      normalizedPartial &&
      !segment.toLowerCase().startsWith(normalizedPartial)
    ) {
      continue
    }

    const fullPath = segments.slice(0, depth + 1).join(".")
    const hasChildren = catalog.some((entry) =>
      entry.path.startsWith(`${fullPath}.`)
    )
    const isLeaf = !hasChildren
    const existing = seen.get(segment)

    if (existing) {
      if (isLeaf && !existing.isLeaf) {
        seen.set(segment, {
          segment,
          isLeaf: false,
          fullPath,
        })
      }
      continue
    }

    seen.set(segment, {
      segment,
      isLeaf,
      type: isLeaf ? attribute.type : undefined,
      fullPath,
    })
  }

  return [...seen.values()].sort((left, right) =>
    left.segment.localeCompare(right.segment)
  )
}

export function getRelationTypeCompletions(
  relationTypes: string[],
  prefix: string
): Completion[] {
  const normalized = prefix.toLowerCase()
  return relationTypes
    .filter(
      (relationType) =>
        !normalized || relationType.toLowerCase().startsWith(normalized)
    )
    .map((relationType) => ({
      label: relationType,
      type: "enum",
      detail: "relation type",
    }))
}

export function getRelationDirectionCompletions(
  prefix: string
): Completion[] {
  const normalized = prefix.toLowerCase()
  return RELATION_DIRECTIONS.filter(
    (direction) => !normalized || direction.startsWith(normalized)
  ).map((direction) => ({
    label: direction,
    type: "keyword",
    detail: "relation direction",
  }))
}

function createSegmentApply(segment: string, isLeaf: boolean): Completion["apply"] {
  return (view, _completion, from, to) => {
    const insert = isLeaf ? segment : `${segment}.`
    view.dispatch({
      changes: { from, to, insert },
      selection: { anchor: from + insert.length },
    })
    if (!isLeaf) {
      startCompletion(view)
    }
  }
}

function attributePathCompletions(
  context: CompletionContext
): CompletionResult | null {
  const pathContext = getAttrPathPrefixAt(context.state, context.pos)
  if (!pathContext) {
    return null
  }

  const { prefix, from: pathStart, to } = pathContext
  const { completedPath, partialSegment, replaceFrom, replaceTo } =
    splitAttrPathPrefix(pathStart, prefix, to)

  const segments = getNextSegmentCompletions(
    attributeCatalog,
    completedPath,
    partialSegment
  )

  if (segments.length === 0) {
    return null
  }

  const options: Completion[] = segments.map((entry) => ({
    label: entry.segment,
    type: entry.isLeaf ? "property" : "namespace",
    detail: entry.isLeaf ? (entry.type ?? "unknown") : entry.fullPath,
    apply: createSegmentApply(entry.segment, entry.isLeaf),
  }))

  return {
    from: replaceFrom,
    to: replaceTo,
    options,
    validFor: /^[\w.]*$/,
    filter: false,
  }
}

function relationCallCompletions(
  context: CompletionContext
): CompletionResult | null {
  const relationContext = getRelationCallContextAt(context.state, context.pos)
  if (!relationContext) {
    return null
  }

  const options =
    relationContext.argument === "type"
      ? getRelationTypeCompletions(relationTypeCatalog, relationContext.prefix)
      : getRelationDirectionCompletions(relationContext.prefix)

  if (options.length === 0) {
    return null
  }

  return {
    from: relationContext.from,
    to: relationContext.to,
    options,
    validFor: /^[\w.]*$/,
    filter: false,
  }
}

function isInsideQuotedFunctionArg(state: EditorState, pos: number) {
  return (
    getAttrPathPrefixAt(state, pos) !== null ||
    getRelationCallContextAt(state, pos) !== null
  )
}

function generalCompletions(context: CompletionContext): CompletionResult | null {
  if (isInsideQuotedFunctionArg(context.state, context.pos)) {
    return null
  }

  const word = context.matchBefore(/[\w.]*/)
  if (!word && !context.explicit) {
    return null
  }

  return {
    from: word ? word.from : context.pos,
    options: [
      ...KEYWORD_COMPLETIONS,
      ...FUNCTION_COMPLETIONS,
      ...FIELD_COMPLETIONS,
      ...SNIPPET_COMPLETIONS,
    ],
    validFor: /^[\w.]*$/,
  }
}

function relicqlCompletionSource(context: CompletionContext): CompletionResult | null {
  const relationMatch = relationCallCompletions(context)
  if (relationMatch) {
    return relationMatch
  }

  const attributeMatch = attributePathCompletions(context)
  if (attributeMatch) {
    return attributeMatch
  }

  return generalCompletions(context)
}

function maybeStartQuotedArgCompletion(update: ViewUpdate) {
  if (!update.docChanged && !update.selectionSet) {
    return
  }

  const status = completionStatus(update.state)
  if (status === "active" || status === "pending") {
    return
  }

  const pos = update.state.selection.main.head
  if (!isInsideQuotedFunctionArg(update.state, pos)) {
    return
  }

  startCompletion(update.view)
}

export const relicqlAutocompletion: Extension = [
  Prec.highest(
    autocompletion({
      override: [relicqlCompletionSource],
      activateOnTyping: true,
      activateOnTypingDelay: 0,
      maxRenderedOptions: 50,
      defaultKeymap: false,
    })
  ),
  Prec.highest(keymap.of(completionKeymap)),
  EditorView.updateListener.of(maybeStartQuotedArgCompletion),
]
