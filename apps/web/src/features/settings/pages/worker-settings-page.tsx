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
import { DurationSettingField } from "@/features/settings/components/setting-fields"
import { usePatchSettings, useSettings } from "@/features/settings/hooks/use-settings"
import {
  settingValueMap,
  workerSettingFields,
} from "@/features/settings/lib/setting-keys"

export function WorkerSettingsPage() {
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
        workerSettingFields.map((field) => [
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

    for (const field of workerSettingFields) {
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

  return (
    <PageShell maxWidth="5xl">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Worker</h1>
        <p className="mt-4 text-sm/7 text-muted-foreground">
          Tune worker polling, retry, and settings refresh intervals. Changes
          apply at runtime without restarting the worker.
        </p>
      </header>

      <Card className="mt-8">
        <CardHeader>
          <CardTitle>Runtime settings</CardTitle>
          <CardDescription>
            Values are stored in the database and picked up by the worker on the
            next settings refresh.
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
              {workerSettingFields.map((field) => (
                <DurationSettingField
                  key={field.key}
                  definition={field}
                  value={values[field.key] ?? field.defaultValue}
                  onChange={(nextValue) =>
                    setValues((current) => ({
                      ...current,
                      [field.key]: nextValue,
                    }))
                  }
                />
              ))}

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
