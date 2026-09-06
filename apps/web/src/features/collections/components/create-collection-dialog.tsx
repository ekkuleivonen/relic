import * as React from "react"
import { Loader2Icon, PlusIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useBuckets } from "@/features/buckets/hooks/use-buckets"
import { useCreateCollection } from "@/features/collections/hooks/use-collections"
import { PithosysqlEditor } from "@/features/search/components/pithosysql-editor"
import {
  BUILTIN_SEARCH_ATTRIBUTES,
  DEFAULT_PITHOSYSQL_QUERY,
} from "@/features/search/constants"
import { useSearchAttributes } from "@/features/search/hooks/use-search-attributes"
import { useSearchRelationTypes } from "@/features/search/hooks/use-search-relation-types"
import { useValidateSearch } from "@/features/search/hooks/use-search-validate"
import { extractApiError } from "@/lib/api"

type CreateCollectionDialogProps = {
  triggerLabel?: string
  initialQuery?: string
  open?: boolean
  onOpenChange?: (open: boolean) => void
  hideTrigger?: boolean
}

export function CreateCollectionDialog(props: CreateCollectionDialogProps) {
  const [internalOpen, setInternalOpen] = React.useState(false)
  const open = props.open ?? internalOpen
  const onOpenChange = props.onOpenChange ?? setInternalOpen
  return (
    <CreateCollectionDialogContent
      key={`${open}:${props.initialQuery ?? ""}`}
      {...props}
      open={open}
      onOpenChange={onOpenChange}
    />
  )
}

function CreateCollectionDialogContent({
  triggerLabel = "Create collection",
  initialQuery,
  open: controlledOpen,
  onOpenChange,
  hideTrigger = false,
}: CreateCollectionDialogProps) {
  const [internalOpen, setInternalOpen] = React.useState(false)
  const open = controlledOpen ?? internalOpen
  const setOpen = onOpenChange ?? setInternalOpen

  const [name, setName] = React.useState("")
  const [description, setDescription] = React.useState("")
  const [query, setQuery] = React.useState(initialQuery ?? DEFAULT_PITHOSYSQL_QUERY)
  const [validationError, setValidationError] = React.useState<string | null>(
    null
  )

  const createCollection = useCreateCollection()
  const validateSearch = useValidateSearch()
  const bucketsQuery = useBuckets()
  const searchAttributes = useSearchAttributes()
  const searchRelationTypes = useSearchRelationTypes()

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

  const bucketNames = React.useMemo(
    () =>
      (bucketsQuery.data?.buckets ?? [])
        .map((bucket) => bucket.name)
        .sort((left, right) => left.localeCompare(right)),
    [bucketsQuery.data?.buckets]
  )


  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()

    const trimmedName = name.trim()
    const trimmedQuery = query.trim()
    if (!trimmedName) {
      setValidationError("Collection name is required.")
      return
    }
    if (!trimmedQuery) {
      setValidationError("Enter a PithosysQL query before saving.")
      return
    }

    setValidationError(null)

    try {
      await validateSearch.mutateAsync(trimmedQuery)
    } catch (error) {
      setValidationError(extractApiError(error))
      return
    }

    try {
      await createCollection.mutateAsync({
        name: trimmedName,
        description: description.trim(),
        query: trimmedQuery,
      })
      setOpen(false)
    } catch {
      // Error presentation is handled by the mutation's onError toast.
    }
  }

  const isSubmitting = createCollection.isPending || validateSearch.isPending

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {!hideTrigger && (
        <DialogTrigger asChild>
          <Button>
            <PlusIcon />
            {triggerLabel}
          </Button>
        </DialogTrigger>
      )}
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Create collection</DialogTitle>
          <DialogDescription>
            Save a PithosysQL query as a reusable collection. Membership updates
            automatically as objects match the query.
          </DialogDescription>
        </DialogHeader>

        <form className="grid gap-4" onSubmit={(event) => void handleSubmit(event)}>
          <div className="grid gap-2">
            <Label htmlFor="collection-name">Name</Label>
            <Input
              id="collection-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Finance PDFs"
              autoFocus
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="collection-description">Description</Label>
            <Textarea
              id="collection-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Optional context for this collection"
              rows={2}
            />
          </div>

          <div className="grid gap-2">
            <Label>PithosysQL query</Label>
            <PithosysqlEditor
              value={query}
              onChange={setQuery}
              attributes={attributes}
              relationTypes={searchRelationTypes.data?.relation_types ?? []}
              bucketNames={bucketNames}
            />
          </div>

          {validationError && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {validationError}
            </div>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <Loader2Icon className="animate-spin" />
                  Saving...
                </>
              ) : (
                "Create collection"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
