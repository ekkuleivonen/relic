# Third-party dependency inventory

Direct frontend dependencies and their installed package metadata. This is an inventory, not an ownership or legal review. Full transitive versions are recorded in `apps/web/package-lock.json`; Go versions are recorded in `go.mod` and `go.sum`. Preserve upstream license notices when redistributing bundled code.

| Package | Installed version | Declared license |
| --- | --- | --- |
| @codemirror/autocomplete | 6.20.3 | MIT |
| @codemirror/lang-sql | 6.10.0 | MIT |
| @codemirror/language | 6.12.4 | MIT |
| @codemirror/lint | 6.9.7 | MIT |
| @codemirror/state | 6.7.0 | MIT |
| @codemirror/view | 6.43.3 | MIT |
| @fontsource-variable/inter | 5.2.8 | OFL-1.1 |
| @lezer/common | 1.5.2 | MIT |
| @lezer/highlight | 1.2.3 | MIT |
| @lezer/lr | 1.4.10 | MIT |
| @tailwindcss/vite | 4.3.1 | MIT |
| @tanstack/react-query | 5.101.0 | MIT |
| @uiw/react-codemirror | 4.25.10 | MIT |
| class-variance-authority | 0.7.1 | Apache-2.0 |
| clsx | 2.1.1 | MIT |
| lucide-react | 1.21.0 | ISC |
| radix-ui | 1.6.0 | MIT |
| react | 19.2.7 | MIT |
| react-dom | 19.2.7 | MIT |
| react-router | 8.3.1 | MIT |
| recharts | 3.8.0 | MIT |
| shadcn | 4.11.0 | MIT |
| sonner | 2.0.7 | MIT |
| tailwind-merge | 3.6.0 | MIT |
| tailwindcss | 4.3.1 | MIT |
| tw-animate-css | 1.4.0 | MIT |

Inter font files are distributed under the SIL Open Font License; the full license is retained in [Inter-OFL.txt](third-party/Inter-OFL.txt). Lucide icons declare ISC; React and shadcn declare MIT. Dependencies retain their own licenses independently of the pending Pithosys license.

Go direct dependencies include AWS SDK for Go v2 (Apache-2.0), Smithy Go (Apache-2.0), go-oidc (Apache-2.0), Huma (MIT), golang-migrate (MIT), pgx (MIT), nats.go (Apache-2.0), and golang.org/x libraries (BSD-3-Clause). Review the exact module LICENSE files before distributing binaries; this summary does not replace those notices. Container base images and Versity Gateway also carry their own licenses.
