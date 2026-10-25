# 0003: A check that did not run scores zero

**Status:** accepted, 25 October 2026

The confidence score (§5.5) gives 1.5 points for style and 1.0 for build and
links. If Vale or lychee is missing, the check did not run, so it earns no
points and the report says so. A score must only reflect checks that ran.

Two more rules from building it:

- A literal matches its source only as a whole token: `1` does not match `120`.
- A writer's sentences in a docs pull request have no source map entry. The
  docs-checks workflow marks them "writer-authored" instead of failing them;
  the writer is their source. Sentences the agent wrote are still checked
  against their sources after the writer edits.
