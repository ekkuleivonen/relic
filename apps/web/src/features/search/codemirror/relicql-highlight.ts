import { styleTags, tags as t } from "@lezer/highlight"

export const relicqlHighlight = styleTags({
  RelicAttr: t.special(t.function(t.variableName)),
  RelicRelation: t.special(t.function(t.typeName)),
})
