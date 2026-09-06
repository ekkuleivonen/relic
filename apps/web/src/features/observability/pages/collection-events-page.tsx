import { PageShell } from "@/components/page-shell"
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

export function CollectionEventsPage() {
  return (
    <PageShell>
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          Collection events
        </h1>
        <p className="mt-4 max-w-2xl text-sm/7 text-muted-foreground">
          Pithosys will emit catalog and workflow events to external systems here.
        </p>
      </header>

      <section className="mt-8">
        <Card>
          <CardHeader>
            <CardTitle>Coming soon</CardTitle>
            <CardDescription>
              Collection event delivery and replay are not available yet. This
              view will show emitted notifications, delivery status, and retry
              history once the feature ships.
            </CardDescription>
          </CardHeader>
        </Card>
      </section>
    </PageShell>
  )
}
