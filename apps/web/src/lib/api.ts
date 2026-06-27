export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "/api"

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(message: string, status: number, detail: unknown) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
  }
}

type ApiRequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown
}

export function extractApiError(error: unknown) {
  if (error instanceof ApiError) {
    if (typeof error.detail === "string") {
      return error.detail
    }

    if (
      typeof error.detail === "object" &&
      error.detail !== null &&
      "message" in error.detail &&
      typeof error.detail.message === "string"
    ) {
      return error.detail.message
    }

    return error.message
  }

  if (error instanceof Error) {
    return error.message
  }

  return "Something went wrong"
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {}
): Promise<T> {
  const headers = new Headers(options.headers)
  const hasBody = options.body !== undefined

  if (hasBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    credentials: "include",
    cache: "no-store",
    body: hasBody ? JSON.stringify(options.body) : undefined,
  })

  if (!response.ok) {
    const detail = await readResponseBody(response)
    throw new ApiError(
      getErrorMessage(detail, response.status),
      response.status,
      detail
    )
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

async function readResponseBody(response: Response) {
  const contentType = response.headers.get("content-type")

  if (contentType?.includes("application/json")) {
    const body = await response.json()
    return "detail" in body ? body.detail : body
  }

  return response.text()
}

function getErrorMessage(detail: unknown, status: number) {
  if (typeof detail === "string" && detail.length > 0) {
    return detail
  }

  if (
    typeof detail === "object" &&
    detail !== null &&
    "message" in detail &&
    typeof detail.message === "string"
  ) {
    return detail.message
  }

  return `Request failed with status ${status}`
}
