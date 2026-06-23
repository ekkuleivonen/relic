import { Route, Routes } from "react-router"

import { AdminHomePage } from "@/app/admin-home-page"
import { BucketDetailPage } from "@/features/buckets/pages/bucket-detail-page"
import { BucketsPage } from "@/features/buckets/pages/buckets-page"

export function App() {
  return (
    <Routes>
      <Route path="/" element={<AdminHomePage />} />
      <Route path="/buckets" element={<BucketsPage />} />
      <Route path="/buckets/:bucketId" element={<BucketDetailPage />} />
    </Routes>
  )
}

export default App
