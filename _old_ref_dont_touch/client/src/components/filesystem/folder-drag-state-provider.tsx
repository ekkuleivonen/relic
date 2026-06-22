import {
  FolderDragStateContext,
  type FolderDragState,
} from "@/hooks/use-folder-drag-state"

type Props = {
  state: FolderDragState
  children: React.ReactNode
}

export function FolderDragStateProvider({ state, children }: Props) {
  return (
    <FolderDragStateContext.Provider value={state}>
      {children}
    </FolderDragStateContext.Provider>
  )
}
