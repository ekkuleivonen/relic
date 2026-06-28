import { Route, Routes } from "react-router"

import { AdminHomePage } from "@/app/admin-home-page"
import { AppLayout } from "@/components/app-layout"
import { RequireSession } from "@/components/layout/route-guards"
import { BucketDetailPage } from "@/features/buckets/pages/bucket-detail-page"
import { BucketsPage } from "@/features/buckets/pages/buckets-page"
import { CollectionDetailPage } from "@/features/collections/pages/collection-detail-page"
import { CollectionsPage } from "@/features/collections/pages/collections-page"
import { JobRunDetailPage } from "@/features/job-runs/pages/job-run-detail-page"
import { JobRunsPage } from "@/features/job-runs/pages/job-runs-page"
import { ObjectDetailPage } from "@/features/objects/pages/object-detail-page"
import { ObjectsPage } from "@/features/objects/pages/objects-page"
import { JobsSettingsPage } from "@/features/settings/pages/jobs-settings-page"
import { UpstreamCapturePage } from "@/features/settings/pages/upstream-capture-page"
import { WorkerSettingsPage } from "@/features/settings/pages/worker-settings-page"
import { UsersPage } from "@/features/users/pages/users-page"
import { LoginPage } from "@/pages/login-page"

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireSession />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<AdminHomePage />} />
          <Route path="/buckets" element={<BucketsPage />} />
          <Route path="/buckets/:bucketId" element={<BucketDetailPage />} />
          <Route path="/job-runs" element={<JobRunsPage />} />
          <Route path="/job-runs/:jobRunId" element={<JobRunDetailPage />} />
          <Route path="/objects" element={<ObjectsPage />} />
          <Route path="/objects/:objectId" element={<ObjectDetailPage />} />
          <Route path="/collections" element={<CollectionsPage />} />
          <Route
            path="/collections/:collectionId"
            element={<CollectionDetailPage />}
          />
          <Route path="/settings/upstream-capture" element={<UpstreamCapturePage />} />
          <Route element={<RequireSession requireAdmin />}>
            <Route path="/users" element={<UsersPage />} />
            <Route path="/settings/worker" element={<WorkerSettingsPage />} />
            <Route path="/settings/jobs" element={<JobsSettingsPage />} />
          </Route>
        </Route>
      </Route>
    </Routes>
  )
}

export default App
