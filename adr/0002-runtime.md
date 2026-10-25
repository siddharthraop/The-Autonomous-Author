# 0002: The agent runs in GitHub Actions; Cloud Run is the next step

**Status:** accepted, 25 October 2026

The design runs the agent on Cloud Run, the run log in BigQuery, and the drift
check as a Cloud Run job started by Cloud Scheduler (§5.7).

**Decision.** The proof of concept runs the same `author` package in a GitHub
Actions runner:

| Design | Proof of concept | Cost |
| --- | --- | --- |
| Agent on Cloud Run | `autonomous-author` workflow on push to `main` | Free on public repositories |
| BigQuery run log | `runlog` branch, JSON lines; mirrored to BigQuery when `AUTHOR_BQ_TABLE` is set | Free |
| Cloud Scheduler and a Cloud Run job | `drift-check` workflow on a daily schedule | Free |
| Gemini key in Secret Manager | Same: read through Workload Identity Federation | 1 secret version |

**Why.** The success test is the draft on every code change. The Actions
runtime meets it with zero Google Cloud compute, inside the foundation rule
that the six builds use at most 20% of each free tier. GitHub writes stay in
GitHub, so no GitHub token is stored in Google Cloud.

**Next.** Containerise `author` as a Cloud Run job (max 1 task), as MANIFEST
did, when traces in Cloud Trace are needed. The workflow then calls
`gcloud run jobs execute` and opens the pull request from the job's output.
