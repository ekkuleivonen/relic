import { Loader2Icon, PlayIcon } from "lucide-react"
import * as React from "react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { RelicqlEditor } from "@/features/search/components/relicql-editor"
import { DEFAULT_RELICQL_QUERY, BUILTIN_SEARCH_ATTRIBUTES } from "@/features/search/constants"
import { useSearchAttributes } from "@/features/search/hooks/use-search-attributes"
import { useSearchExecute } from "@/features/search/hooks/use-search-execute"
import { useValidateSearch } from "@/features/search/hooks/use-search-validate"
import { ObjectsTable } from "@/features/objects/components/objects-table"
import { extractApiError } from "@/lib/api"

type ObjectsSearchPanelProps = {
  bucketId?: string
}

export function ObjectsSearchPanel({ bucketId }: ObjectsSearchPanelProps) {
  const [draftQuery, setDraftQuery] = React.useState(DEFAULT_RELICQL_QUERY)
  const [submittedQuery, setSubmittedQuery] = React.useState<string | null>(null)
  const [validationError, setValidationError] = React.useState<string | null>(
    null
  )

  const searchAttributes = useSearchAttributes()
  const attributes = React.useMemo(() => {
    const fromApi = searchAttributes.data?.attributes ?? []
    if (fromApi.length === 0) {
      return BUILTIN_SEARCH_ATTRIBUTES
    }

    const merged = new Map<string, (typeof fromApi)[number]>()
    for (const attribute of [...BUILTIN_SEARCH_ATTRIBUTES, ...fromApi]) {
      merged.set(attribute.path, attribute)
    }

    return [...merged.values()].sort((left, right) =>
      left.path.localeCompare(right.path)
    )
  }, [searchAttributes.data?.attributes])
  const validateSearch = useValidateSearch()
  const executeQuery = useSearchExecute({
    query: submittedQuery ?? "",
    bucketId,
    enabled: submittedQuery !== null && validationError === null,
  })

  const handleSubmit = React.useCallback(
    async (query = draftQuery) => {
      const trimmed = query.trim()
      if (!trimmed) {
        setValidationError("Enter a RelicQL query before running search.")
        setSubmittedQuery(null)
        return
      }

      setValidationError(null)

      try {
        await validateSearch.mutateAsync(trimmed)
        setSubmittedQuery(trimmed)
      } catch (error) {
        setValidationError(extractApiError(error))
        setSubmittedQuery(null)
      }
    },
    [draftQuery, validateSearch]
  )

  React.useEffect(() => {
    void handleSubmit(DEFAULT_RELICQL_QUERY)
    // Validate and run the default query once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const objects = executeQuery.data?.objects ?? []
  const isRunning = validateSearch.isPending || executeQuery.isFetching

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>RelicQL search</CardTitle>
            <CardDescription>
              Write RelicQL, then run search to validate and fetch matching
              objects.
            </CardDescription>
          </div>
          <Button
            size="sm"
            onClick={() => void handleSubmit()}
            disabled={isRunning}
          >
            {isRunning ? (
              <Loader2Icon className="animate-spin" />
            ) : (
              <PlayIcon />
            )}
            Run search
          </Button>
        </div>
      </CardHeader>
      <CardContent className="grid gap-4">
        <RelicqlEditor
          value={draftQuery}
          onChange={setDraftQuery}
          attributes={attributes}
          onSubmit={() => void handleSubmit()}
        />

        {validationError && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3">
            <div className="font-medium text-destructive">Query invalid</div>
            <p className="mt-1 text-sm text-destructive/90">{validationError}</p>
          </div>
        )}

        <SearchStatusLine
          draftQuery={draftQuery}
          submittedQuery={submittedQuery}
          isRunning={isRunning}
          hasValidationError={validationError !== null}
          resultCount={objects.length}
        />

        {executeQuery.isLoading && (
          <div className="flex items-center gap-3 rounded-lg border px-4 py-6 text-sm text-muted-foreground">
            <Loader2Icon className="size-4 animate-spin" />
            Running search...
          </div>
        )}

        {executeQuery.isError && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-6">
            <div className="font-medium text-destructive">Search failed</div>
            <p className="mt-1 text-sm text-muted-foreground">
              {extractApiError(executeQuery.error)}
            </p>
            <Button
              className="mt-4"
              variant="outline"
              onClick={() => void executeQuery.refetch()}
            >
              Retry
            </Button>
          </div>
        )}

        {executeQuery.isSuccess && objects.length === 0 && (
          <div className="rounded-lg border border-dashed px-4 py-8 text-center">
            <div className="font-medium">No objects matched</div>
            <p className="mt-1 text-sm text-muted-foreground">
              Try broadening the query or sync a bucket first.
            </p>
          </div>
        )}

        {objects.length > 0 && <ObjectsTable objects={objects} />}
      </CardContent>
    </Card>
  )
}

type SearchStatusLineProps = {
  draftQuery: string
  submittedQuery: string | null
  isRunning: boolean
  hasValidationError: boolean
  resultCount: number
}

function SearchStatusLine({
  draftQuery,
  submittedQuery,
  isRunning,
  hasValidationError,
  resultCount,
}: SearchStatusLineProps) {
  if (!draftQuery.trim()) {
    return (
      <p className="text-sm text-muted-foreground">
        Enter a RelicQL query to search objects.
      </p>
    )
  }

  if (isRunning) {
    return (
      <p className="text-sm text-muted-foreground">Running search...</p>
    )
  }

  if (hasValidationError) {
    return (
      <p className="text-sm text-muted-foreground">
        Fix the query error above, then run search again.
      </p>
    )
  }

  if (!submittedQuery) {
    return (
      <p className="text-sm text-muted-foreground">
        Press Run search to validate and fetch results.
      </p>
    )
  }

  if (draftQuery.trim() !== submittedQuery.trim()) {
    return (
      <p className="text-sm text-muted-foreground">
        Query changed since last run. Press Run search to refresh results.
      </p>
    )
  }

  return (
    <p className="text-sm text-muted-foreground">
      {resultCount} object{resultCount === 1 ? "" : "s"} matched.
    </p>
  )
}
