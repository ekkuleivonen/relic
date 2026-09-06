# Security

Pithosys is alpha software for trusted operators. It has not received an independent security audit. Use an isolated evaluation deployment until the release checklist is closed.

Report vulnerabilities through [GitHub private vulnerability reporting](https://github.com/elei-io/pithosys/security/advisories/new). If that form is unavailable, contact the repository owner privately; do not put credentials or exploit details in public issues.

## Deployment boundary

Administrators can configure upstream endpoints and credentials and initiate jobs. Endpoints may be private because self-hosted S3 is supported. Treat administrator access as authority to make network requests from the worker; enforce network egress restrictions around the deployment. Use bucket-scoped read-only credentials for real catalogs. The synthetic demo seeder alone needs write access to its disposable S3 service.

Use HTTPS for any non-local deployment and set `WEB_APP_URL` to its exact origin so cookies are secure. Keep the database, S3 service, and worker private. Session/encryption keys must be randomly generated, kept outside Git, backed up securely, and preserved across restarts. Losing the encryption key makes stored credentials unreadable.

The API checks write permissions centrally, protects browser writes against cross-origin requests, caps request bodies at 1 MiB, bounds search size/depth/results, and applies request deadlines. Login throttling is process-local and based on the direct peer address. Behind a proxy, add an external rate limiter configured for that proxy topology; all clients otherwise share the proxy's quota. These controls do not constitute comprehensive denial-of-service protection.

## Historical exposure

The September 2026 audit identified six credential values in old Git history. Their configuration maps to local/self-hosted Garage S3 services and their RPC connections; none of those six was identified as a third-party service credential. The owner accepts the homelab-only exposure and has elected not to require rotation for those services. Reuse elsewhere was not established, and no credentials were tested or revoked. Deleting current files does not erase clones/caches. Do not reuse historical example credentials.

CI scans the current tracked snapshot and new commits. The separately dispatched **Full history secret audit** scans all fetched refs and is expected to report the known historical findings until cleanup is approved and completed. A green normal CI run is not a clean-history certification.

## Dependency audit scope

Both package-manager audits and GitHub advisories are reviewed: their databases and reachability models differ. The September 2026 update removes the known vulnerable frontend versions and upgrades Go cryptography/compression dependencies to patched releases. `govulncheck` reports no affected symbols or imported packages. It still identifies the unmaintained `golang.org/x/crypto/openpgp` package at module level; Pithosys does not import that package, and the advisory has no patched release. This is retained as an explicit audit limitation, not silently dismissed as a fixed vulnerability.
