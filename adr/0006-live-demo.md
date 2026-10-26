# 0006: A live demo app, and DITA as a second output

**Status:** accepted, 26 October 2026

**Why.** The success test is an end-user experience: someone describes a feature,
commits it, and gets a first draft for review, in DITA and in docs as code. Asking a
reviewer to edit Python on GitHub and read Actions logs doesn't meet it. MANIFEST
proved the pattern: a console on GitHub Pages with a small API on Cloud Run.

**Decision.**

- `app/` is a static page on GitHub Pages. A visitor picks one of four sample
  features (or writes their own), sees the exact code change, and commits it.
- `api/` (Cloud Run service `author-api`, 0 to 1 instance, request-based billing)
  copies `sample/` into a sandbox Git repository, applies the feature as a real
  commit, and runs the same `author` engine the GitHub workflow runs: the same
  rules, Gemini step, checks and score. Stages stream to the page as they happen.
- Visitors never run code: a feature is a small set of validated edits to the
  sample settings file.
- Each sample states what a good draft does. The app checks the draft against
  that and shows expected versus actual.
- The writer answers the agent's questions in the page, the checks run again,
  and approval unlocks only when every question is answered and every check
  passes. The draft downloads as a .zip with MyST, DITA, the report and diffs.

**DITA.** The agent edits one source, the MyST pages, where the checks run, and
`author/dita.py` writes the same pages as DITA 1.3 topics and a map:
substitutions become `<keyword keyref>` keys defined in the map, questions become
`<draft-comment>`, and tables become `<simpletable>`. Every run is validated
against the OASIS DITA 1.3 DTDs (vendored in `vendor/dita13`, from DITA-OT 4.4)
with `xmllint`. Topics are generic `<topic>` elements for now; mapping the doc
ticket's doc type to concept, task or reference is the next step.

**Cost.** Each run takes a few seconds of one vCPU, far inside the 20% free-tier
share. A per-visitor and a global hourly limit protect the free Gemini quota. If
the model call fails, the run still completes with rules and questions.
