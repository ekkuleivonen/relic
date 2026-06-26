import { Link } from "react-router"
import { ArrowLeftIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { ObjectsCard } from "@/features/objects/components/objects-card"

export function ObjectsPage() {
  return (
    <main className="min-h-svh bg-background text-foreground">
      <div className="mx-auto w-full max-w-7xl px-6 py-8 lg:px-8">
        <Button variant="ghost" asChild>
          <Link to="/">
            <ArrowLeftIcon />
            Back home
          </Link>
        </Button>

        <header className="mt-6">
          <div className="flex items-center gap-3">
            <img src="/logo.svg" alt="" className="size-9 rounded-lg" />
            <div>
              <div className="text-xs text-muted-foreground">Relic admin</div>
              <h1 className="text-2xl font-semibold tracking-tight">Objects</h1>
            </div>
          </div>
          <p className="mt-4 max-w-2xl text-sm/7 text-muted-foreground">
            Search and inspect object catalog rows created by bucket sync jobs.
          </p>
        </header>

        <section className="mt-8">
          <ObjectsCard />
        </section>
      </div>
    </main>
  )
}
