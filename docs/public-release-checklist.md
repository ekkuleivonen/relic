# Public release readiness

Status: preparation in progress. The GitHub repository was already public when this review began; no visibility change was made.

## License and credential decisions

- The owner confirmed publication rights and selected the MIT license, with `elei.io` as the copyright holder.
- All six historical credential findings map to local/self-hosted Garage services. The owner accepts homelab-only exposure; rotation is not a release requirement for those services. No third-party service credential was identified among these findings. Reuse elsewhere remains unverified.
- Publishing a coordinated Git history rewrite remains a separate pending action. A private clean candidate is prepared; existing clones, forks, cached views, and old tags require separate handling.

## Engineering acceptance

- [x] Full PostgreSQL tests with the race detector and Go vet pass.
- [x] Frontend lint/build and dependency audits pass.
- [x] Isolated synthetic demo works from a clean checkout.
- [x] CI runs on GitHub and required checks protect main.
- [x] Current snapshot/new commits pass secret scanning.
- [ ] Full published history passes secret scanning after approved cleanup.
- [x] Screenshots and a reproducible small-scale measurement are documented.
- [x] Review deployment boundaries and alpha limitations before inviting real workloads.

This checklist tracks evidence, not a guarantee of security or production readiness. OIDC needs a deployment-specific identity-provider test; large-scale behavior and multi-worker failure recovery need broader operational validation.

A private candidate history was scrubbed and scanned with no findings. It has not been published; licensing does not rewrite the existing Git history.
