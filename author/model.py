"""Tool 3, the model step: Gemini drafts and revises through Agent Development Kit.

Three modes, as in MANIFEST:
  gemini    live calls to gemini-3.8-flash (key from Secret Manager, via the workflow)
  scripted  recorded responses from a JSON file, for tests and replays
  none      no model; fixed rules run and every change item a rule cannot cover
            becomes a [NEEDS INPUT] question
The model never scores its own work and never sees a check result it can change.
"""
import json
import os

SYSTEM = """You draft documentation updates for a docs-as-code repository written in MyST Markdown.
You receive change items (C1, C2 ...) read from a merged code change, the doc ticket (T1), the PR
description (S-PR) and the affected pages (P1, P2 ...) with line numbers. Fixed rules have already
updated substitutions and typed copies of replaced values; do not repeat those edits.

Rules:
- Edit only the pages you are given. Follow each page's existing structure and the Google developer
  documentation style guide: second person, present tense, active voice, short sentences.
- Every fact (number, unit, flag, field, command, date, region) must appear in a source you cite.
- If a reader needs a fact that no source gives, write [NEEDS INPUT: <one question>] instead. Never guess.
- Cover every change item that a fixed rule did not already cover.
Return JSON only:
{"edits": [{"path": "docs/...md", "find": "<exact text that exists once in the page>",
            "replace": "<the new text, which may include the found text>"}],
 "sentences": [{"text": "<each new or changed sentence, exactly as written>", "sources": ["C1", "P1"]}]}
"""

REVISE = """Some sentences in your draft failed the fixed checks. Rewrite only those sentences.
Give each a source that contains every literal in it, or replace it with [NEEDS INPUT: <question>].
Return JSON only: {"fixes": [{"old": "<failed sentence>", "new": "<replacement>", "sources": ["C1"]}]}
"""


class NoModel:
    id = "none"

    def draft(self, prompt):
        return {"edits": [], "sentences": []}

    def revise(self, prompt):
        return {"fixes": []}


class ScriptedModel:
    """Replays recorded responses: {"draft": {...}, "revise": [{...}, ...]}."""

    def __init__(self, path):
        with open(path) as f:
            self.data = json.load(f)
        self.id = self.data.get("model", "scripted")
        self._rev = list(self.data.get("revise", []))

    def draft(self, prompt):
        return self.data.get("draft", {"edits": [], "sentences": []})

    def revise(self, prompt):
        return self._rev.pop(0) if self._rev else {"fixes": []}


class GeminiModel:
    def __init__(self, model_id=None):
        from google.adk.agents import LlmAgent
        from google.adk.runners import InMemoryRunner
        from google.genai import types
        self.id = model_id or os.environ.get("AUTHOR_MODEL", "gemini-3.8-flash")
        self._types = types
        cfg = types.GenerateContentConfig(temperature=0.2, response_mime_type="application/json")
        self._runners = {}
        for name, instruction in (("drafter", SYSTEM), ("reviser", SYSTEM + "\n" + REVISE)):
            agent = LlmAgent(name=name, model=self.id, instruction=instruction, generate_content_config=cfg)
            self._runners[name] = InMemoryRunner(agent=agent, app_name="autonomous-author")
        self.tokens = {"input": 0, "output": 0}

    def _ask(self, name, prompt):
        runner = self._runners[name]
        session = runner.session_service.create_session_sync(app_name="autonomous-author", user_id="ci")
        msg = self._types.Content(role="user", parts=[self._types.Part(text=prompt)])
        text = ""
        for ev in runner.run(user_id="ci", session_id=session.id, new_message=msg):
            um = getattr(ev, "usage_metadata", None)
            if um:
                self.tokens["input"] += um.prompt_token_count or 0
                self.tokens["output"] += um.candidates_token_count or 0
            if ev.content and ev.content.parts:
                text += "".join(p.text or "" for p in ev.content.parts)
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        return json.loads(text)

    def draft(self, prompt):
        return self._ask("drafter", prompt)

    def revise(self, prompt):
        return self._ask("reviser", prompt)


def load(spec):
    if spec == "gemini":
        return GeminiModel()
    if spec and spec.startswith("scripted:"):
        return ScriptedModel(spec.split(":", 1)[1])
    return NoModel()
