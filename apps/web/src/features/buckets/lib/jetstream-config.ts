import type { BucketUpstreamConfig } from "@/types/buckets"

export type JetStreamFormState = {
  enabled: boolean
  url: string
  stream: string
  subject: string
  consumer: string
}

export function emptyJetStreamFormState(): JetStreamFormState {
  return {
    enabled: false,
    url: "",
    stream: "",
    subject: "",
    consumer: "",
  }
}

export function jetstreamFormFromUpstreamConfig(
  upstreamConfig: BucketUpstreamConfig,
): JetStreamFormState {
  const jetstream = isRecord(upstreamConfig.jetstream)
    ? upstreamConfig.jetstream
    : null
  if (!jetstream) {
    return emptyJetStreamFormState()
  }

  const url = typeof jetstream.url === "string" ? jetstream.url : ""
  const stream = typeof jetstream.stream === "string" ? jetstream.stream : ""
  const subject =
    typeof jetstream.subject === "string" ? jetstream.subject : ""
  const consumer =
    typeof jetstream.consumer === "string" ? jetstream.consumer : ""
  const enabled =
    url !== "" || stream !== "" || subject !== "" || consumer !== ""

  return {
    enabled,
    url,
    stream,
    subject,
    consumer,
  }
}

export function upstreamConfigWithJetstream(
  existing: BucketUpstreamConfig,
  form: JetStreamFormState,
): BucketUpstreamConfig {
  const next: BucketUpstreamConfig = { ...existing }

  if (!form.enabled) {
    delete next.jetstream
    return next
  }

  next.jetstream = {
    url: form.url,
    stream: form.stream,
    subject: form.subject,
    ...(form.consumer ? { consumer: form.consumer } : {}),
  }

  return next
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}
