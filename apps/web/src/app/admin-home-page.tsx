import {
  ArchiveIcon,
  ListFilterIcon,
  RefreshCwIcon,
} from "lucide-react"
import { Link } from "react-router"

import { useTheme } from "@/components/theme-provider"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

const nextSteps = [
  {
    title: "Connect buckets",
    description: "Create S3-compatible bucket connections from the admin UI.",
    icon: ArchiveIcon,
  },
  {
    title: "Import inventory",
    description: "Run the initial scan that turns object storage into catalog data.",
    icon: RefreshCwIcon,
  },
  {
    title: "Browse objects",
    description: "List and filter imported objects by bucket, prefix, type, and size.",
    icon: ListFilterIcon,
  },
] as const

export function AdminHomePage() {
  const { theme, setTheme } = useTheme()
  const nextTheme = theme === "dark" ? "light" : "dark"

  return (
    <main className="min-h-svh bg-background text-foreground">
      <div className="mx-auto flex min-h-svh w-full max-w-6xl flex-col px-6 py-8 lg:px-8">
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <img src="/logo.svg" alt="" className="size-9 rounded-lg shadow-sm" />
            <div>
              <div className="text-sm font-semibold tracking-tight">Relic</div>
              <div className="text-xs text-muted-foreground">
                Every byte in its place.
              </div>
            </div>
          </div>
          <Button variant="outline" onClick={() => setTheme(nextTheme)}>
            {nextTheme === "dark" ? "Dark" : "Light"} mode
          </Button>
        </header>

        <section className="grid flex-1 items-center gap-8 py-16 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="max-w-2xl">
            <Badge variant="outline">Admin preview</Badge>
            <h1 className="mt-6 text-4xl font-semibold tracking-tight text-balance lg:text-6xl">
              Hello from Relic admin.
            </h1>
            <p className="mt-5 max-w-xl text-sm/7 text-muted-foreground lg:text-base/8">
              This is the first web surface for Relic: a metadata and discovery
              platform for object storage. The next screen can start the bucket
              administration loop.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button size="lg" asChild>
                <Link to="/buckets">Buckets UI next</Link>
              </Button>
              <Button size="lg" variant="outline" asChild>
                <a href="/api/docs">View API docs</a>
              </Button>
            </div>
          </div>

          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle>First admin flow</CardTitle>
              <CardDescription>
                The scaffold is ready for the MVP bucket workflow.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3">
              {nextSteps.map((item) => (
                <div
                  key={item.title}
                  className="flex gap-3 rounded-lg border bg-background/60 p-3"
                >
                  <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <item.icon className="size-4" aria-hidden="true" />
                  </div>
                  <div>
                    <div className="text-sm font-medium">{item.title}</div>
                    <p className="mt-1 text-xs/6 text-muted-foreground">
                      {item.description}
                    </p>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  )
}
