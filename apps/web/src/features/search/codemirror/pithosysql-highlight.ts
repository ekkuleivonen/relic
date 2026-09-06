import { styleTags, tags as t } from "@lezer/highlight"

export const pithosysqlHighlight = styleTags({
  PithosysAttr: t.special(t.function(t.variableName)),
  PithosysRelation: t.special(t.function(t.typeName)),
})
