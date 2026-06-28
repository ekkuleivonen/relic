import * as React from "react"
import { PencilIcon } from "lucide-react"

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
import { useUpdateCollection } from "@/features/collections/hooks/use-collections"
import { RelicqlEditor } from "@/features/search/components/relicql-editor"
import { BUILTIN_SEARCH_ATTRIBUTES } from "@/features/search/constants"
import { useSearchAttributes } from "@/features/search/hooks/use-search-attributes"
import { useSearchRelationTypes } from "@/features/search/hooks/use-search-relation-types"
import { useValidateSearch } from "@/features/search/hooks/use-search-validate"
import { extractApiError } from "@/lib/api"
import type { Collection } from "@/types/collections"

type EditCollectionDialogProps = {
  collection: Collection
}

export function EditCollectionDialog({ collection }: EditCollectionDialogProps) {
  const [open, setOpen] = React.useState(false)
  const [name, setName] = React.useState(collection.name)
  const [description, setDescription] = React.useState(collection.description)
  const [query, setQuery] = React.useState(collection.query)
  const [validationError, setValidationError] = React.useState<string | null>(
    null
  )

  const updateCollection = useUpdateCollection(collection.id)
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

  React.useEffect(() => {
    if (!open) {
      return
    }

    setName(collection.name)
    setDescription(collection.description)
    setQuery(collection.query)
    setValidationError(null)
  }, [open, collection])

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()

    const trimmedName = name.trim()
    const trimmedQuery = query.trim()
    if (!trimmedName) {
      setValidationError("Collection name is required.")
      return
    }
    if (!trimmedQuery) {
      setValidationError("Enter a RelicQL query before saving.")
      return
    }

    setValidationError(null)

    if (trimmedQuery !== collection.query.trim()) {
      try {
        await validateSearch.mutateAsync(trimmedQuery)
      } catch (error) {
        setValidationError(extractApiError(error))
        return
      }
    }

    try {
      await updateCollection.mutateAsync({
        name: trimmedName,
        description: description.trim(),
        query: trimmedQuery,
      })
      setOpen(false)
    } catch {
      // Error presentation is handled by the mutation's onError toast.
    }
  }

  const isSubmitting = updateCollection.isPending || validateSearch.isPending

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <PencilIcon />
          Edit
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Edit collection</DialogTitle>
          <DialogDescription>
            Update the collection metadata or saved RelicQL query.
          </DialogDescription>
        </DialogHeader>

        <form className="grid gap-4" onSubmit={(event) => void handleSubmit(event)}>
          <div className="grid gap-2">
            <Label htmlFor="edit-collection-name">Name</Label>
            <Input
              id="edit-collection-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="edit-collection-description">Description</Label>
            <Textarea
              id="edit-collection-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={2}
            />
          </div>

          <div className="grid gap-2">
            <Label>RelicQL query</Label>
            <RelicqlEditor
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
              {isSubmitting ? "Saving..." : "Save changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
