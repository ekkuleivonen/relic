import * as React from "react"
import { Loader2Icon } from "lucide-react"

import { PageShell } from "@/components/page-shell"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  BooleanSettingField,
  DurationSettingField,
} from "@/features/settings/components/setting-fields"
import { usePatchSettings, useSettings } from "@/features/settings/hooks/use-settings"
import {
  formatBooleanSetting,
  jobsSettingFields,
  parseBooleanSetting,
  settingValueMap,
} from "@/features/settings/lib/setting-keys"

export function JobsSettingsPage() {
  const settingsQuery = useSettings()
  const patchSettings = usePatchSettings()
  const [values, setValues] = React.useState<Record<string, string>>({})

  React.useEffect(() => {
    if (!settingsQuery.data) {
      return
    }

    const map = settingValueMap(settingsQuery.data)
    setValues(
      Object.fromEntries(
        jobsSettingFields.map((field) => [
          field.key,
          map[field.key] ?? field.defaultValue,
        ]),
      ),
    )
  }, [settingsQuery.data])

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!settingsQuery.data) {
      return
    }

    const original = settingValueMap(settingsQuery.data)
    const updates: Record<string, string> = {}

    for (const field of jobsSettingFields) {
      const nextValue = values[field.key] ?? field.defaultValue
      const currentValue = original[field.key] ?? field.defaultValue
      if (nextValue !== currentValue) {
        updates[field.key] = nextValue
      }
    }

    if (Object.keys(updates).length === 0) {
      return
    }

    try {
      await patchSettings.mutateAsync(updates)
    } catch {
      // Toast handled by mutation onError.
    }
  }

  const scanEnabled = parseBooleanSetting(
    values.SCAN_BUCKET_ENABLED ?? "true",
  )
  const duplicateDetectionEnabled = parseBooleanSetting(
    values.DUPLICATE_DETECTION_ENABLED ?? "false",
  )

  return (
    <PageShell maxWidth="5xl">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>
        <p className="mt-4 text-sm/7 text-muted-foreground">
          Control global scheduled jobs and their cadence. Per-bucket scan
          settings are no longer used; scan timing applies to all buckets.
        </p>
      </header>

      <Card className="mt-8">
        <CardHeader>
          <CardTitle>Scheduled jobs</CardTitle>
          <CardDescription>
            Enable or disable background schedulers and configure how often they
            run.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {settingsQuery.isError ? (
            <p className="text-sm text-destructive">
              Failed to load settings. Try refreshing the page.
            </p>
          ) : settingsQuery.isLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2Icon className="size-4 animate-spin" />
              Loading settings...
            </div>
          ) : (
            <form className="space-y-6" onSubmit={handleSubmit}>
              {jobsSettingFields.map((field) => {
                const value = values[field.key] ?? field.defaultValue

                if (field.type === "boolean") {
                  return (
                    <BooleanSettingField
                      key={field.key}
                      definition={field}
                      checked={parseBooleanSetting(value)}
                      onCheckedChange={(checked) =>
                        setValues((current) => ({
                          ...current,
                          [field.key]: formatBooleanSetting(checked),
                        }))
                      }
                    />
                  )
                }

                const disabled =
                  (field.key === "SCAN_BUCKET_INTERVAL" && !scanEnabled) ||
                  (field.key === "DUPLICATE_DETECTION_INTERVAL" &&
                    !duplicateDetectionEnabled)

                return (
                  <DurationSettingField
                    key={field.key}
                    definition={field}
                    value={value}
                    disabled={disabled}
                    onChange={(nextValue) =>
                      setValues((current) => ({
                        ...current,
                        [field.key]: nextValue,
                      }))
                    }
                  />
                )
              })}

              <div className="flex justify-end">
                <Button type="submit" disabled={patchSettings.isPending}>
                  {patchSettings.isPending ? (
                    <>
                      <Loader2Icon className="size-4 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    "Save changes"
                  )}
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>
    </PageShell>
  )
}
