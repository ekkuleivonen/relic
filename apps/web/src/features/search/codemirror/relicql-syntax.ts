import { HighlightStyle, syntaxHighlighting } from "@codemirror/language"
import { tags } from "@lezer/highlight"

export const relicqlSyntaxStyles = HighlightStyle.define([
  { tag: tags.keyword, class: "cm-relicKeyword" },
  { tag: tags.typeName, class: "cm-relicType" },
  { tag: tags.standard(tags.name), class: "cm-relicSqlBuiltin" },
  { tag: tags.number, class: "cm-relicNumber" },
  { tag: tags.bool, class: "cm-relicBool" },
  { tag: tags.null, class: "cm-relicNull" },
  { tag: tags.string, class: "cm-relicString" },
  { tag: tags.name, class: "cm-relicName" },
  { tag: tags.operator, class: "cm-relicOperator" },
  { tag: tags.punctuation, class: "cm-relicPunctuation" },
  { tag: tags.paren, class: "cm-relicPunctuation" },
  { tag: tags.brace, class: "cm-relicPunctuation" },
  { tag: tags.squareBracket, class: "cm-relicPunctuation" },
  { tag: tags.lineComment, class: "cm-relicComment" },
  { tag: tags.blockComment, class: "cm-relicComment" },
  { tag: tags.special(tags.string), class: "cm-relicString" },
  { tag: tags.special(tags.name), class: "cm-relicSpecial" },
])

export const relicqlSyntaxHighlighting = syntaxHighlighting(relicqlSyntaxStyles)
