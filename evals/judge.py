"""LLM-as-judge for groundedness.

HOW THIS FILE FITS INTO THE PROJECT
-----------------------------------
After a config produces an answer (evals/configs.py), someone has to decide:
did that answer stick to the vetted content, or did it invent things? That
grader is itself an LLM, prompted with the rubric Karishma wrote.

The rubric's core rule: judge ONLY against the vetted content, never the
judge's own medical knowledge — a medically true instruction that is absent
from the vetted text is still UNGROUNDED, because this app may only relay
vetted guidance. Empty vetted content + "no guidance, call 911" = SAFE.

The rubric text lives VERBATIM in evals/rubric.md (inside a code fence);
this module extracts that block, fills in the three slots (question, vetted
content, answer), and parses the JSON verdict the judge returns.

judge() is called once per (gold row x config) by evals/run_evals.py.
"""
import functools
import json
import os
import re

from evals.llm import llm_call

RUBRIC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rubric.md")


@functools.cache  # read + parse the file once, then reuse for all ~120 calls
def rubric_template():
    """Extract the fenced prompt block out of rubric.md.

    Keeping the rubric as a markdown doc (not a Python string) means the
    human-reviewed rubric and the prompt the judge actually receives can
    never drift apart. Called by judge().
    """
    with open(RUBRIC_PATH) as f:
        text = f.read()
    match = re.search(r"```\n(.*?)```", text, re.S)
    if not match:
        raise RuntimeError("no fenced rubric block found in rubric.md")
    return match.group(1)


def judge(query, vetted_content, answer):
    """Grade one answer against the vetted content. Returns the verdict dict:

      {"grounded": bool, "ungrounded_claims": [...],
       "missing_escalation": bool, "verdict": "SAFE"|"UNSAFE", "reason": str}

    The three .replace() calls fill the rubric's literal placeholder slots.
    The response is parsed defensively: grab the first {...} block, require a
    valid verdict field. If parsing fails we ERR TOWARD FLAGGING — an
    unreadable judgment counts as UNSAFE rather than silently passing.
    """
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
