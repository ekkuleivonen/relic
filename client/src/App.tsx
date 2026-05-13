import { Navigate, Route, Routes } from "react-router"

import { AdminLayout } from "@/components/layout/admin-layout"
import { RequireSession } from "@/components/layout/route-guards"
import { AdminPlaceholderPage } from "@/pages/admin/admin-placeholder-page"
import { AccessKeysPage } from "@/pages/admin/access-keys-page"
import { AuditEventsPage } from "@/pages/admin/audit-events-page"
import { BucketsPage } from "@/pages/admin/buckets-page"
import { FileEventsPage } from "@/pages/admin/file-events-page"
import { FolderAccessPage } from "@/pages/admin/folder-access-page"
import { MaintenanceEventsPage } from "@/pages/admin/maintenance-events-page"
import { ProcessorsPage } from "@/pages/admin/processors-page"
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
          <Route index element={<Navigate to="/admin/buckets" replace />} />
          <Route path="buckets" element={<BucketsPage />} />
          <Route path="users" element={<UsersPage />} />
          <Route path="access-keys" element={<AccessKeysPage />} />
          <Route path="folders" element={<FolderAccessPage />} />
          <Route path="audit-events" element={<AuditEventsPage />} />
          <Route path="file-events" element={<FileEventsPage />} />
          <Route path="maintenance-events" element={<MaintenanceEventsPage />} />
          <Route path="processors" element={<ProcessorsPage />} />
          <Route
            path="files"
            element={
              <AdminPlaceholderPage
                title="Files"
                description="Inspect logical file references and metadata."
              />
            }
          />
          <Route
            path="blobs"
            element={
              <AdminPlaceholderPage
                title="Blobs"
                description="Inspect physical blob placement, refcounts, and migration state."
              />
            }
          />
        </Route>
      </Route>
      <Route element={<RequireSession />}>
        <Route path="/search" element={<SearchPage />} />
        <Route path="/folder/:folderId" element={<FilesystemPage />} />
        <Route path="/file/:fileId" element={<FileDetailPage />} />
        <Route path="*" element={<FilesystemPage />} />
      </Route>
    </Routes>
  )
}

export default App
