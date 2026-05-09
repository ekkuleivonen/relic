import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

type AdminPlaceholderPageProps = {
  title: string
  description: string
}

export function AdminPlaceholderPage({
  title,
  description,
}: AdminPlaceholderPageProps) {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Coming next</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          This admin section will follow the Buckets pattern: typed API calls,
          React Query hooks, and focused CRUD components.
        </CardContent>
      </Card>
    </div>
  )
}
