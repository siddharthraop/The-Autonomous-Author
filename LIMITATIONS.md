# Limitations of version 0.2

The Autonomous Author is a proof of concept. This page lists what version 0.2 can't do
yet, why, and what to do instead. It ends with an extract of what a run produces.

## What version 0.2 does

When a code change merges, the agent reads it, finds every docs page it affects, makes
the edits that need no wording with fixed rules, asks Gemini to word the rest, checks
every sentence against its source, scores the draft and hands it to a writer. The draft
comes in docs as code (MyST Markdown) and DITA 1.3. You can try it in the
[live demo](https://siddharthraop.github.io/The-Autonomous-Author/app/) or through the
GitHub workflow in this repository.

## Limitations and alternatives

| # | Limitation | Why | Alternative now | Planned |
| --- | --- | --- | --- | --- |
| 1 | It drafts only from **code changes to its sample product**, natctl. You can't paste a feature description from another product, such as a `gcloud` command, and get a draft. | The design drafts from the code change, because the code is the source of truth. The change reader understands one product's settings file. | In the demo, use **Write your own**: choose a natctl timeout and a change, and describe it in your words. | A text-only mode that drafts a new topic from a feature description, with every fact checked against that text. A change reader per product: CLI definitions, OpenAPI specs or YANG models. |
| 2 | The change reader detects five kinds of change: a changed default, a new setting, a new `describe` field, a renamed flag and a new or changed attribute (such as a minimum). It **doesn't detect removals, deprecations, renamed settings or changes in behaviour** inside functions. | Each kind needs its own reliable parser; a guessed change item would let the model write about things that didn't happen. | The writer reviews the code PR for these. A change with nothing the reader can see produces "no docs change", not a wrong draft. | Removal and deprecation items, which mark pages for a deprecation notice. |
| 3 | It **edits existing pages only**. It doesn't create a new page for a new feature. | A new page needs an outline decision that the doc kickoff makes. | When no page fits, the change item becomes a `[NEEDS INPUT]` question on the closest page. | Create a new topic from the doc ticket's doc type and pages fields. |
| 4 | The **DITA is generated from the MyST draft**, not edited in place. Topics are generic `<topic>` elements, values are keys, questions are `<draft-comment>`. There's no conref, profiling (DITAVAL) or concept, task and reference specialization yet. | One source keeps the checks in one place. Every run is validated against the OASIS DITA 1.3 DTDs. | For a DITA-first team, migrate with [MANIFEST](https://siddharthraop.github.io/Manifest/) and review the draft in DITA. | Map the doc type to concept, task or reference. An option to edit the DITA source directly, with the same checks. |
| 5 | **Gemini output varies** between runs of the same feature. The free tier has rate limits, and the demo allows 10 runs an hour per visitor and 60 in total. | Language models aren't deterministic. The free tier keeps the cost at zero. | The checks catch unsourced facts on every run. If the model fails or a limit is hit, the run still completes with rules and questions, and the report says so. | Replay recorded runs; the paid tier or Vertex AI for steady load. |
| 6 | The checks verify **literal facts**: numbers, units, flags, field names and code. A sentence can quote correct facts and still mean something wrong. | Checking meaning needs a person, or a second model whose output must also be checked. | A writer reads every draft; the agent can't merge. | An evaluation set of past changes, scored before a new model or prompt goes live (design §5.6). |
| 7 | The demo is a **sandbox**. Drafts are kept in memory for an hour and are lost when the service scales to zero. There's no sign-in, and nothing is published. | It keeps the demo free and safe to open to anyone. | Use the GitHub workflow for the real path: it opens a draft pull request that persists. | None for the demo. |
| 8 | **Jira** is supported through the Jira Cloud REST API but hasn't been tested against a live Jira site. The demo makes its own doc ticket; the workflow uses a GitHub issue. | No Jira site was available for the proof of concept. | Link a GitHub issue with `Doc ticket: #N` in the commit message. | Test against a Jira Cloud free site. |
| 9 | **Monitoring is partial**. The run log works (on the `runlog` branch), but the drift check needs 30 runs before it reports. The BigQuery mirror, Cloud Trace export and Firebase preview sites aren't configured. | Each needs a one-time setup and isn't needed to show the draft. | Read the run log on the `runlog` branch; the demo's preview tab shows the built page. | Set `AUTHOR_BQ_TABLE` and the Firebase secret; export ADK traces. |
| 10 | **Style** checks use the Vale Google package on changed lines only. The preview uses Sphinx's default theme, not a production theme. | It's the documented house style of the design; one theme keeps the build small. | A writer applies team-specific style in review. | Add a team style package learned from review edits (tool 8 already proposes rules). |

## An extract: the hard case

This extract is from the demo's sample **New default for new gateways only**, the third
change in the design document. The developer wrote: "Lower the TCP TIME_WAIT default to
30 seconds for new gateways. Existing gateways keep 120 seconds." The code adds
`"default": 30` and `"legacy_default": 120`. This run used fixed rules only (no model), so
it is the same every time. With Gemini, the questions are usually replaced by sourced
sentences.

**The value, changed once in the docs-as-code source (rule R-01):**

```diff
--- a/docs/substitutions.yml
+++ b/docs/substitutions.yml
@@ -1,4 +1,4 @@
 nat_tcp_established_default: 1200 seconds
 nat_tcp_transitory_default: 30 seconds
-nat_tcp_time_wait_default: 120 seconds
+nat_tcp_time_wait_default: 30 seconds
 nat_udp_default: 30 seconds
```

**The page that still says 120 seconds is kept, because 120 is still true for existing
gateways. What the change doesn't explain becomes a question, not a guess:**

```diff
--- a/docs/nat/troubleshooting.md
+++ b/docs/nat/troubleshooting.md
@@ -7,4 +7,8 @@
 with `--tcp-time-wait-timeout`.
 
+[NEEDS INPUT: C2 — TCP TIME_WAIT: legacy_default changed from not set to 120 seconds. How should this page describe it?]
+
+[NEEDS INPUT: C1 — TCP TIME_WAIT default changed from 120 to 30 seconds. How should this page describe it?]
+
 ## Idle connections drop
```

**The same draft in DITA 1.3: the key in the map, and the questions as draft comments:**

```diff
--- a/dita/docs.ditamap
+++ b/dita/docs.ditamap
@@ -5,5 +5,5 @@
   <keydef keys="nat-tcp-established-default"><topicmeta><keywords><keyword>1200 seconds</keyword></keywords></topicmeta></keydef>
   <keydef keys="nat-tcp-transitory-default"><topicmeta><keywords><keyword>30 seconds</keyword></keywords></topicmeta></keydef>
-  <keydef keys="nat-tcp-time-wait-default"><topicmeta><keywords><keyword>120 seconds</keyword></keywords></topicmeta></keydef>
+  <keydef keys="nat-tcp-time-wait-default"><topicmeta><keywords><keyword>30 seconds</keyword></keywords></topicmeta></keydef>
   <keydef keys="nat-udp-default"><topicmeta><keywords><keyword>30 seconds</keyword></keywords></topicmeta></keydef>
   <topicref href="nat/tune-nat-configuration.dita"/>
```

```diff
--- a/dita/nat/troubleshooting.dita
+++ b/dita/nat/troubleshooting.dita
@@ -6,4 +6,6 @@
     <section id="connections-are-reused-too-early"><title>Connections are reused too early</title>
     <p>A closed TCP connection stays in TIME_WAIT for 120 seconds before its port can be reused. If new connections fail because no ports are free, lower the value with <codeph>--tcp-time-wait-timeout</codeph>.</p>
+    <p><draft-comment author="autonomous-author" disposition="open">NEEDS INPUT: C2 — TCP TIME_WAIT: legacy_default changed from not set to 120 seconds. How should this page describe it?</draft-comment></p>
+    <p><draft-comment author="autonomous-author" disposition="open">NEEDS INPUT: C1 — TCP TIME_WAIT default changed from 120 to 30 seconds. How should this page describe it?</draft-comment></p>
     </section>
     <section id="idle-connections-drop"><title>Idle connections drop</title>
```

**Compared with what a good draft for this feature does:**

```text
✓ The new default is set once, in the substitution file
✓ The DITA key nat-tcp-time-wait-default says 30 seconds
✓ 120 seconds stays where it's still true for existing gateways
✓ No invented rollout date or region
✓ Every new sentence has a checked source, or is a question for the developer
✓ The docs build passes (Sphinx, warnings as errors)
✓ The DITA output is valid DITA 1.3
```

Confidence: 9.0 / 10, review closely. The two open questions cost 0.5 points each and stop
the draft being marked ready. When the writer answers them in the demo, the checks run
again, the score returns to 10 and **Approve draft** unlocks.
