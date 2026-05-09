import { Navigate, Route, Routes } from "react-router"

import { AdminLayout } from "@/components/layout/admin-layout"
import { RequireSession } from "@/components/layout/route-guards"
import { AdminPlaceholderPage } from "@/pages/admin/admin-placeholder-page"
import { BucketsPage } from "@/pages/admin/buckets-page"
import { UsersPage } from "@/pages/admin/users-page"
import { FilesystemPage } from "@/pages/filesystem-page"
import { LoginPage } from "@/pages/login-page"

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireSession requireAdmin />}>
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<Navigate to="/admin/buckets" replace />} />
          <Route path="buckets" element={<BucketsPage />} />
          <Route path="users" element={<UsersPage />} />
          <Route
            path="access-keys"
            element={
              <AdminPlaceholderPage
                title="Access Keys"
                description="Mint and revoke SigV4 access keys."
              />
            }
          />
          <Route
            path="folders"
            element={
              <AdminPlaceholderPage
                title="Folders"
                description="Manage virtual folders, schemas, policies, and ACLs."
              />
            }
          />
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
        <Route path="*" element={<FilesystemPage />} />
      </Route>
    </Routes>
  )
}

export default App
