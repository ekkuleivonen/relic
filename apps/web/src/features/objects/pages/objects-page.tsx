import { PageShell } from "@/components/page-shell"
import { ObjectsSearchPanel } from "@/features/objects/components/objects-search-panel"

export function ObjectsPage() {
  return (
    <PageShell>
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Objects</h1>
        <p className="mt-4 max-w-2xl text-sm/7 text-muted-foreground">
          Search catalog objects with PithosysQL and inspect matching rows.
        </p>
      </header>

      <section className="mt-8">
        <ObjectsSearchPanel />
      </section>
    </PageShell>
  )
}
