import { HighlightStyle, syntaxHighlighting } from "@codemirror/language"
import { tags } from "@lezer/highlight"

export const pithosysqlSyntaxStyles = HighlightStyle.define([
  { tag: tags.keyword, class: "cm-pithosysKeyword" },
  { tag: tags.typeName, class: "cm-pithosysType" },
  { tag: tags.standard(tags.name), class: "cm-pithosysSqlBuiltin" },
  { tag: tags.number, class: "cm-pithosysNumber" },
  { tag: tags.bool, class: "cm-pithosysBool" },
  { tag: tags.null, class: "cm-pithosysNull" },
  { tag: tags.string, class: "cm-pithosysString" },
  { tag: tags.name, class: "cm-pithosysName" },
  { tag: tags.operator, class: "cm-pithosysOperator" },
  { tag: tags.punctuation, class: "cm-pithosysPunctuation" },
  { tag: tags.paren, class: "cm-pithosysPunctuation" },
  { tag: tags.brace, class: "cm-pithosysPunctuation" },
  { tag: tags.squareBracket, class: "cm-pithosysPunctuation" },
  { tag: tags.lineComment, class: "cm-pithosysComment" },
  { tag: tags.blockComment, class: "cm-pithosysComment" },
  { tag: tags.special(tags.string), class: "cm-pithosysString" },
  { tag: tags.special(tags.name), class: "cm-pithosysSpecial" },
])

export const pithosysqlSyntaxHighlighting = syntaxHighlighting(pithosysqlSyntaxStyles)
