import { ExternalTokenizer } from "@lezer/lr"

import { relicAttr, relicRelation, text } from "./relicql.parser.terms"

const QUOTE = 39
const LPAREN = 40
const RPAREN = 41
const COMMA = 44

function isSpace(code: number) {
  return code === 9 || code === 10 || code === 11 || code === 12 || code === 13 || code === 32
}

function isIdentPart(code: number) {
  return (
    code === 95 ||
    (code >= 48 && code <= 57) ||
    (code >= 65 && code <= 90) ||
    (code >= 97 && code <= 122)
  )
}

function equalsCaseInsensitive(input: { peek: (offset: number) => number }, word: string) {
  for (let index = 0; index < word.length; index += 1) {
    const code = input.peek(index)
    if (code === -1) {
      return false
    }

    const actual = String.fromCharCode(code).toLowerCase()
    if (actual !== word[index]) {
      return false
    }
  }

  const trailing = input.peek(word.length)
  if (trailing !== -1 && isIdentPart(trailing)) {
    return false
  }

  return true
}

function skipSpaces(input: { peek: (offset: number) => number }, start: number) {
  let offset = start
  while (isSpace(input.peek(offset))) {
    offset += 1
  }

  return offset
}

function readQuotedStringLength(input: { peek: (offset: number) => number }, start: number) {
  if (input.peek(start) !== QUOTE) {
    return null
  }

  let offset = start + 1
  while (true) {
    const code = input.peek(offset)
    if (code === -1) {
      return null
    }

    if (code === QUOTE) {
      if (input.peek(offset + 1) === QUOTE) {
        offset += 2
        continue
      }

      return offset - start + 1
    }

    if (code === 92) {
      offset += 2
      continue
    }

    offset += 1
  }
}

function matchRelicAttr(input: { peek: (offset: number) => number }) {
  if (!equalsCaseInsensitive(input, "attr")) {
    return null
  }

  let offset = skipSpaces(input, 4)
  if (input.peek(offset) !== LPAREN) {
    return null
  }

  offset = skipSpaces(input, offset + 1)
  const pathLength = readQuotedStringLength(input, offset)
  if (pathLength === null) {
    return null
  }

  offset = skipSpaces(input, offset + pathLength)
  if (input.peek(offset) !== RPAREN) {
    return null
  }

  return offset + 1
}

function matchRelicRelation(input: { peek: (offset: number) => number }) {
  if (!equalsCaseInsensitive(input, "has_relation")) {
    return null
  }

  let offset = skipSpaces(input, "has_relation".length)
  if (input.peek(offset) !== LPAREN) {
    return null
  }

  offset = skipSpaces(input, offset + 1)
  const typeLength = readQuotedStringLength(input, offset)
  if (typeLength === null) {
    return null
  }

  offset = skipSpaces(input, offset + typeLength)

  if (input.peek(offset) === COMMA) {
    offset = skipSpaces(input, offset + 1)
    const directionLength = readQuotedStringLength(input, offset)
    if (directionLength === null) {
      return null
    }

    offset = skipSpaces(input, offset + directionLength)
  }

  if (input.peek(offset) !== RPAREN) {
    return null
  }

  return offset + 1
}

function matchRelicCallAt(input: { peek: (offset: number) => number }) {
  return matchRelicAttr(input) ?? matchRelicRelation(input)
}

function readPlainTextLength(input: { peek: (offset: number) => number }) {
  if (input.peek(0) === -1) {
    return 0
  }

  let length = 1
  while (input.peek(length) !== -1) {
    const nextInput = {
      peek: (offset: number) => input.peek(length + offset),
    }
    if (matchRelicCallAt(nextInput) !== null) {
      break
    }

    length += 1
  }

  return length
}

export const relicOverlay = new ExternalTokenizer((input) => {
  const start = input.pos
  const attrLength = matchRelicAttr(input)
  if (attrLength !== null) {
    input.acceptTokenTo(relicAttr, start + attrLength)
    return
  }

  const relationLength = matchRelicRelation(input)
  if (relationLength !== null) {
    input.acceptTokenTo(relicRelation, start + relationLength)
    return
  }

  const textLength = readPlainTextLength(input)
  if (textLength === 0) {
    return
  }

  input.acceptTokenTo(text, start + textLength)
})
