# Public release readiness

Status: preparation in progress. The GitHub repository was already public when this review began; no visibility change was made.

## Owner decisions still required

- Confirm ownership and permission to publish the code and included assets; select and add a license. Public visibility alone does not grant an open-source license.
- Establish whether historical credential-like values were ever valid; revoke or rotate affected S3 access keys and Garage RPC secrets where applicable. Do not paste values into issues or chat.
- Approve a coordinated history rewrite after rotation. Existing clones, forks, cached views, and old tags need separate handling. Preserve any required private backup securely.

## Engineering acceptance

- [x] Full PostgreSQL tests with the race detector and Go vet pass.
- [x] Frontend lint/build and dependency audits pass.
- [x] Isolated synthetic demo works from a clean checkout.
- [ ] CI runs on GitHub and required checks protect main.
- [x] Current snapshot/new commits pass secret scanning.
- [ ] Full published history passes secret scanning after approved cleanup.
- [x] Screenshots and a reproducible small-scale measurement are documented.
- [x] Review deployment boundaries and alpha limitations before inviting real workloads.

This checklist tracks evidence, not a guarantee of security or production readiness. OIDC needs a deployment-specific identity-provider test; large-scale behavior and multi-worker failure recovery need broader operational validation.

A private candidate history was scrubbed and scanned across 102 commits with no findings. It has not been published; the live history remains unchanged pending owner decisions.
