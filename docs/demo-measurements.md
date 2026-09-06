# Local demo measurement — September 6, 2026

A smoke measurement on an Apple Silicon development machine, with API, worker, PostgreSQL 17, and Versity S3 running in Docker. Dataset: 128 synthetic JSON objects across four key prefixes. No real upstream data or credentials were used.

- Initial catalog synchronization: **2.016 seconds**, measured from API bucket registration until all 128 objects were searchable and observed jobs were terminal. Includes worker polling and one-second completion polling; excludes image builds and S3 object seeding.
- Ten sequential authenticated searches (`FROM objects LIMIT 100`): median **2.78 ms**, range **2.51–3.20 ms**, from the demo container to the API over the Docker network. Includes HTTP/JSON overhead; warm database, one client.
- Verified metadata annotation and saved collection creation after sync.

Reproduce with `./scripts/demo.sh up`. Search sample timings are printed by the seeder. `./scripts/demo.sh check` reruns seeding and synchronization against retained data, so it measures a subsequent sync rather than a fresh import.

These numbers establish that the demo works; they do not predict throughput, p95 latency, or capacity. The sample is too small for a meaningful tail-latency estimate. A scale study should add object-count tiers, cold/warm runs, concurrent clients, upstream latency/failure injection, and database/worker resource measurements before publishing performance claims.
