import { Loader2Icon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { DeleteCaptureFieldDialog } from "@/features/settings/components/delete-capture-field-dialog"
import {
  formatCaptureSource,
  formatExtractorType,
} from "@/features/settings/lib/upstream-capture-options"
import { useUpdateUpstreamCaptureField } from "@/features/settings/hooks/use-upstream-capture-fields"
import type { UpstreamCaptureField } from "@/types/upstream-capture"

type CaptureFieldsTableProps = {
  fields: UpstreamCaptureField[]
}

export function CaptureFieldsTable({ fields }: CaptureFieldsTableProps) {
  const updateField = useUpdateUpstreamCaptureField()

  async function handleEnabledChange(field: UpstreamCaptureField, enabled: boolean) {
    try {
      await updateField.mutateAsync({
        id: field.id,
        input: { enabled },
      })
    } catch {
      // Toast handled by mutation onError.
    }
  }

  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-16">On</TableHead>
            <TableHead>Attribute path</TableHead>
            <TableHead>Source</TableHead>
            <TableHead>Extractor</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Origin</TableHead>
            <TableHead className="w-20 text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {fields.map((field) => {
            const isRequired = field.category === "required"
            const isUpdating =
              updateField.isPending && updateField.variables?.id === field.id

            return (
              <TableRow key={field.id}>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <Checkbox
                      checked={field.enabled}
                      disabled={isRequired || isUpdating}
                      onCheckedChange={(checked) =>
                        void handleEnabledChange(field, checked === true)
                      }
                      aria-label={`Toggle ${field.attribute_path}`}
                    />
                    {isUpdating ? (
                      <Loader2Icon className="size-3 animate-spin text-muted-foreground" />
                    ) : null}
                  </div>
                </TableCell>
                <TableCell>
                  <div className="font-mono text-xs">{field.attribute_path}</div>
                  {isRequired ? (
                    <Badge variant="outline" className="mt-1">
                      Required
                    </Badge>
                  ) : null}
                </TableCell>
                <TableCell>{formatCaptureSource(field.capture_source)}</TableCell>
                <TableCell>
                  <div className="text-sm">
                    {formatExtractorType(field.extractor_type)}
                  </div>
                  <div className="mt-0.5 font-mono text-xs text-muted-foreground">
                    {field.extractor_ref}
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant="secondary">{field.value_type}</Badge>
                </TableCell>
                <TableCell>
                  <Badge variant={field.origin === "user" ? "default" : "outline"}>
                    {field.origin}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  {field.origin === "user" ? (
                    <DeleteCaptureFieldDialog field={field} />
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
