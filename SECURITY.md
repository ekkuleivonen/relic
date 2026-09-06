# Security

Pithosys is alpha software for trusted operators. It has not received an independent security audit. Use an isolated evaluation deployment until the release checklist is closed.

Report vulnerabilities through [GitHub private vulnerability reporting](https://github.com/elei-io/pithosys/security/advisories/new). If that form is unavailable, contact the repository owner privately; do not put credentials or exploit details in public issues.

## Deployment boundary

Administrators can configure upstream endpoints and credentials and initiate jobs. Endpoints may be private because self-hosted S3 is supported. Treat administrator access as authority to make network requests from the worker; enforce network egress restrictions around the deployment. Use bucket-scoped read-only credentials for real catalogs. The synthetic demo seeder alone needs write access to its disposable S3 service.

Use HTTPS for any non-local deployment and set `WEB_APP_URL` to its exact origin so cookies are secure. Keep the database, S3 service, and worker private. Session/encryption keys must be randomly generated, kept outside Git, backed up securely, and preserved across restarts. Losing the encryption key makes stored credentials unreadable.

The API checks write permissions centrally, protects browser writes against cross-origin requests, caps request bodies at 1 MiB, bounds search size/depth/results, and applies request deadlines. Login throttling is process-local and based on the direct peer address. Behind a proxy, add an external rate limiter configured for that proxy topology; all clients otherwise share the proxy's quota. These controls do not constitute comprehensive denial-of-service protection.

## Historical exposure

The September 2026 audit identified credential-like values in old Git history. Deleting current files does not revoke credentials or erase clones/caches. Owner confirmation and credential rotation/revocation remain required before the exposure can be considered resolved. Do not reuse historical example credentials.

CI scans the current tracked snapshot and new commits. The separately dispatched **Full history secret audit** scans all fetched refs and is expected to report the known historical findings until cleanup is approved and completed. A green normal CI run is not a clean-history certification.
