# 0004: Three model modes

**Status:** accepted, 25 October 2026

`author draft --model` takes:

- `gemini`: live calls to `gemini-3.8-flash` through Agent Development Kit.
  `auto` picks this when the workflow has read the key from Secret Manager.
- `scripted:<file>`: recorded responses. The tests replay the design
  document's three sample changes (§6) this way.
- `none`: no model. Fixed rules make every edit that needs no wording, and
  every change item a rule cannot cover becomes a `[NEEDS INPUT]` question.

So the success path works before any key exists, and no unchecked fact reaches
a reader in any mode. The model never scores its own work.
