import * as React from "react"

import { useFileUpload } from "@/hooks/use-file-upload"

type UseNativeFileDropArgs = {
  folderId: string
  disabled?: boolean
}

export function useNativeFileDrop({ folderId, disabled }: UseNativeFileDropArgs) {
  const upload = useFileUpload()
  const [isOver, setIsOver] = React.useState(false)
  const dragDepth = React.useRef(0)

  function carriesFiles(event: React.DragEvent) {
    return Array.from(event.dataTransfer?.types ?? []).includes("Files")
  }

  function reset() {
    dragDepth.current = 0
    setIsOver(false)
  }

  const handlers = {
    onDragEnter(event: React.DragEvent) {
      if (disabled || !carriesFiles(event)) return
      event.preventDefault()
      event.stopPropagation()
      dragDepth.current += 1
      setIsOver(true)
    },
    onDragOver(event: React.DragEvent) {
      if (disabled || !carriesFiles(event)) return
      event.preventDefault()
      event.stopPropagation()
      event.dataTransfer.dropEffect = "copy"
      if (!isOver) setIsOver(true)
    },
    onDragLeave(event: React.DragEvent) {
      if (disabled || !carriesFiles(event)) return
      event.preventDefault()
      event.stopPropagation()
      dragDepth.current -= 1
      if (dragDepth.current <= 0) {
        reset()
      }
    },
    onDrop(event: React.DragEvent) {
      if (disabled || !carriesFiles(event)) return
      event.preventDefault()
      event.stopPropagation()
      reset()
      const files = Array.from(event.dataTransfer?.files ?? [])
      void uploadAll(files, folderId, upload)
    },
  }

  return { handlers, isOver }
}

async function uploadAll(
  files: File[],
  folderId: string,
  upload: ReturnType<typeof useFileUpload>
) {
  for (const file of files) {
    try {
      await upload.mutateAsync({ folder_id: folderId, file })
    } catch {
      // toast handled in the hook
    }
  }
}
