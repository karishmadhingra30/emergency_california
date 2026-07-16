"""LLM-as-judge for groundedness. The rubric lives verbatim in rubric.md —
this module extracts the fenced prompt block, fills the slots, and parses the
JSON verdict. Judged ONLY against the vetted content, never the judge's own
medical knowledge. Errs toward flagging: unparseable output = UNSAFE.
"""
import json
import os
import re

from evals.llm import llm_call

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUBRIC_PATH = os.path.join(REPO, "evals", "rubric.md")

_rubric_template = None


def rubric_template():
    global _rubric_template
    if _rubric_template is None:
        with open(RUBRIC_PATH) as f:
            text = f.read()
        match = re.search(r"```\n(.*?)```", text, re.S)
        if not match:
            raise RuntimeError("no fenced rubric block found in rubric.md")
        _rubric_template = match.group(1)
    return _rubric_template


def judge(query, vetted_content, answer):
    prompt = (rubric_template()
              .replace("{user question}", query)
              .replace("{the retrieved entry text, may be empty}",
                       vetted_content or "(empty)")
              .replace("{the assistant's answer}", answer))
    raw = llm_call(prompt, model_role="judge")

    match = re.search(r"\{.*\}", raw, re.S)
    if match:
        try:
            verdict = json.loads(match.group(0))
            if verdict.get("verdict") in ("SAFE", "UNSAFE"):
                return verdict
        except json.JSONDecodeError:
            pass
    # Err toward flagging: an unreadable judgment is treated as UNSAFE.
    return {"grounded": False, "ungrounded_claims": ["JUDGE_PARSE_ERROR"],
            "missing_escalation": False, "verdict": "UNSAFE",
            "reason": f"judge output unparseable: {raw[:120]}"}
