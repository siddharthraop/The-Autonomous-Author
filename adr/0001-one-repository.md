# 0001: One repository for the proof of concept

**Status:** accepted, 25 October 2026

The design shows a code repository and a docs repository (Figure 7). The proof
of concept keeps both in this repository: `product/` is the code, `docs/` is the
MyST docs set and `author/` is the agent.

**Why.** One repository needs no cross-repository token, so the workflow's own
`GITHUB_TOKEN` can open the draft pull request. That keeps credentials out of the
setup, which the Google Cloud rules require.

**What stays the same.** The trigger is a code change (`product/**`), the output
is a draft pull request that changes only `docs/` and `.author/drafts/`, and
`CODEOWNERS` with branch protection makes a writer's approval required. The
agent cannot merge.

**Next.** A separate docs repository needs a GitHub App token with write access
to it. `author draft --target` already takes the base branch; a `--docs-repo`
option is the only change.
