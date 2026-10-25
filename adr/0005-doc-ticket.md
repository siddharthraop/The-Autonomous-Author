# 0005: GitHub issue as the doc ticket when Jira is not configured

**Status:** accepted, 25 October 2026

The design reads a Jira doc ticket (tool 1). The agent finds the ticket from a
line such as `Doc ticket: NAT-1182` or `Doc ticket: #12` in the code pull
request or commit message.

- With `JIRA_BASE_URL`, `JIRA_EMAIL` (repository variables) and
  `JIRA_API_TOKEN` (secret), a key such as `NAT-1182` is read with the Jira
  Cloud REST API v3, and the agent comments on it.
- Otherwise `#12` is read as a GitHub issue. The issue template `Doc ticket`
  has the fields from the doc kickoff: doc type, audience and pages. The agent
  comments with the draft link and score and adds the `docs-review` label,
  which stands for "moved to review".
