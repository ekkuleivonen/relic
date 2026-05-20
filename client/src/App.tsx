import { Navigate, Route, Routes } from "react-router"

import { AdminLayout } from "@/components/layout/admin-layout"
import { RequireSession } from "@/components/layout/route-guards"
import { AccessKeysPage } from "@/pages/admin/access-keys-page"
import { StorageBackendsPage } from "@/pages/admin/storage-backends-page"
import { FolderAccessPage } from "@/pages/admin/folder-access-page"
import { AuditEventsPage } from "@/pages/admin/audit-events-page"
import { UsersPage } from "@/pages/admin/users-page"
import { FileDetailPage } from "@/pages/file-detail-page"
import { FilesystemPage } from "@/pages/filesystem-page"
import { LoginPage } from "@/pages/login-page"
import { SearchPage } from "@/pages/search-page"

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireSession requireAdmin />}>
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<Navigate to="/admin/storage-backends" replace />} />
          <Route path="storage-backends" element={<StorageBackendsPage />} />
          <Route path="users" element={<UsersPage />} />
          <Route path="access-keys" element={<AccessKeysPage />} />
          <Route path="folders" element={<FolderAccessPage />} />
          <Route path="audit-events" element={<AuditEventsPage />} />
        </Route>
      </Route>
      <Route element={<RequireSession />}>
        <Route path="/" element={<FilesystemPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/folder/:folderId" element={<FilesystemPage />} />
        <Route path="/file/:fileId" element={<FileDetailPage />} />
      </Route>
    </Routes>
  )
}

export default App
