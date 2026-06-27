import type { UserAttributeValueType } from "@/types/objects"

export function inferUserAttributeValueType(value: unknown): UserAttributeValueType {
  if (typeof value === "boolean") {
    return "boolean"
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? "integer" : "float"
  }
  if (typeof value === "string" && isTimestampString(value)) {
    return "timestamp"
  }
  return "string"
}

export function formatUserAttributeValue(value: unknown, type: UserAttributeValueType) {
  if (value === null || value === undefined) {
    return ""
  }

  switch (type) {
    case "boolean":
      return typeof value === "boolean" ? String(value) : String(Boolean(value))
    case "integer":
    case "float":
      return typeof value === "number" ? String(value) : String(value)
    case "timestamp":
      return typeof value === "string" ? timestampToLocalInput(value) : String(value)
    case "string":
    default:
      return typeof value === "string" ? value : JSON.stringify(value)
  }
}

export function displayUserAttributeValue(value: unknown, type: UserAttributeValueType) {
  switch (type) {
    case "boolean":
      return value === true ? "true" : value === false ? "false" : String(value)
    case "timestamp":
      if (typeof value === "string" && isTimestampString(value)) {
        return new Intl.DateTimeFormat(undefined, {
          dateStyle: "medium",
          timeStyle: "short",
        }).format(new Date(value))
      }
      return String(value)
    case "integer":
    case "float":
    case "string":
    default:
      return formatUserAttributeValue(value, type)
  }
}

export function parseUserAttributeValue(
  text: string,
  type: UserAttributeValueType
): unknown {
  const trimmed = text.trim()

  switch (type) {
    case "boolean":
      if (trimmed === "true") {
        return true
      }
      if (trimmed === "false") {
        return false
      }
      throw new Error("Boolean values must be true or false.")
    case "integer": {
      if (trimmed === "" || !/^-?\d+$/.test(trimmed)) {
        throw new Error("Integer values must be whole numbers.")
      }
      return Number.parseInt(trimmed, 10)
    }
    case "float": {
      if (trimmed === "" || Number.isNaN(Number(trimmed))) {
        throw new Error("Float values must be valid numbers.")
      }
      return Number.parseFloat(trimmed)
    }
    case "timestamp": {
      if (trimmed === "") {
        throw new Error("Timestamp values are required.")
      }
      const timestamp = localInputToTimestamp(trimmed)
      if (!isTimestampString(timestamp)) {
        throw new Error("Timestamp values must be valid dates.")
      }
      return timestamp
    }
    case "string":
    default:
      return text
  }
}

function isTimestampString(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}T/.test(value)) {
    return false
  }

  return !Number.isNaN(Date.parse(value))
}

function timestampToLocalInput(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  const pad = (part: number) => String(part).padStart(2, "0")
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function localInputToTimestamp(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toISOString()
}
