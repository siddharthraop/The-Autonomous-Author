# Architecture decision records

Decisions made while building the proof of concept from the design document
(`index.html`, v0.1). Each record says where the build follows the design and
where it differs, and why.

| ADR | Decision |
| --- | --- |
| [0001](0001-one-repository.md) | Code, docs and agent in one repository for the proof of concept |
| [0002](0002-runtime.md) | The agent runs in GitHub Actions now; Cloud Run comes next |
| [0003](0003-scoring-honesty.md) | A check that did not run scores zero |
| [0004](0004-model-modes.md) | Three model modes: gemini, scripted, none |
| [0005](0005-doc-ticket.md) | GitHub issue as the doc ticket when Jira is not configured |
