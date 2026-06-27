import { Route, Routes } from "react-router"

import { AdminHomePage } from "@/app/admin-home-page"
import { AppLayout } from "@/components/app-layout"
import { BucketDetailPage } from "@/features/buckets/pages/bucket-detail-page"
import { BucketsPage } from "@/features/buckets/pages/buckets-page"
import { JobRunDetailPage } from "@/features/job-runs/pages/job-run-detail-page"
import { JobRunsPage } from "@/features/job-runs/pages/job-runs-page"
import { ObjectDetailPage } from "@/features/objects/pages/object-detail-page"
import { ObjectsPage } from "@/features/objects/pages/objects-page"
import { UpstreamCapturePage } from "@/features/settings/pages/upstream-capture-page"

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<AdminHomePage />} />
        <Route path="/buckets" element={<BucketsPage />} />
        <Route path="/buckets/:bucketId" element={<BucketDetailPage />} />
        <Route path="/job-runs" element={<JobRunsPage />} />
        <Route path="/job-runs/:jobRunId" element={<JobRunDetailPage />} />
        <Route path="/objects" element={<ObjectsPage />} />
        <Route path="/objects/:objectId" element={<ObjectDetailPage />} />
        <Route path="/settings/upstream-capture" element={<UpstreamCapturePage />} />
      </Route>
    </Routes>
  )
}

export default App
