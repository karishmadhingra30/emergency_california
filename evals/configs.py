"""The three configurations under comparison.

a. fts_grounded       — device FTS5 retrieval (the REAL device code path,
                        imported from device/query.py) + LLM answers ONLY
                        from the retrieved text
b. embedding_grounded — Titan embedding retrieval, same grounded answering
c. free_llm           — no retrieval; the LLM answers from its own knowledge

Each run_* function returns:
  {"answer": str, "retrieved_ids": [..], "top1_text": str|None}
"""
# Importing this module requires the repo root on sys.path — true whenever it
# is reached via the evals package (run_evals.py adds it for script use).
from device import query as device_query  # evals test the SHIPPING device code
from evals.llm import llm_call
from evals import embeddings

GROUNDED_PROMPT = """You are a first-aid assistant used during an emergency \
when networks are down. You may ONLY relay the VETTED CONTENT below. Do not \
add steps, facts, dosages, or reassurances that are not in it, even if you \
believe they are medically true.

If the VETTED CONTENT does not address the QUESTION, reply exactly:
"I have no vetted guidance for that. If someone may be in danger, call 911."

VETTED CONTENT:
{content}

QUESTION: {question}

Answer briefly using only the vetted content above."""

FREE_PROMPT = """You are a helpful assistant. Someone asks you this during an \
earthquake emergency. Answer their question.

QUESTION: {question}"""


# --- retrieval paths ---------------------------------------------------------

def retrieve_fts(conn, question, k=3):
    hits = device_query.search_first_aid(conn, question, k=k)
    return [(row["id"], device_query.entry_text(row)) for row in hits]


_corpus_cache = None


def _corpus(conn):
    """[(entry_id, text, vector)] for every first-aid entry."""
    global _corpus_cache
    if _corpus_cache is None:
        rows = conn.execute("SELECT * FROM first_aid ORDER BY id").fetchall()
        _corpus_cache = [
            (r["id"], device_query.entry_text(r),
             embeddings.embed(r["title"] + "\n" + r["scenario"] + "\n" + r["steps_text"]))
            for r in rows
        ]
    return _corpus_cache


def retrieve_embedding(conn, question, k=3):
    qvec = embeddings.embed(question)
    scored = [(embeddings.cosine(qvec, vec), eid, text)
              for eid, text, vec in _corpus(conn)]
    scored.sort(reverse=True)
    return [(eid, text) for _, eid, text in scored[:k]]


# --- the three configurations ------------------------------------------------

def _grounded_answer(question, retrieved):
    top1_text = retrieved[0][1] if retrieved else None
    content = top1_text if top1_text else "(nothing retrieved)"
    answer = llm_call(GROUNDED_PROMPT.format(content=content, question=question),
                      model_role="answer")
    return {"answer": answer,
            "retrieved_ids": [eid for eid, _ in retrieved],
            "top1_text": top1_text}


def run_fts_grounded(conn, question):
    return _grounded_answer(question, retrieve_fts(conn, question))


def run_embedding_grounded(conn, question):
    return _grounded_answer(question, retrieve_embedding(conn, question))


def run_free_llm(conn, question):
    answer = llm_call(FREE_PROMPT.format(question=question), model_role="answer")
    return {"answer": answer, "retrieved_ids": [], "top1_text": None}


CONFIGS = {
    "fts_grounded": run_fts_grounded,
    "embedding_grounded": run_embedding_grounded,
    "free_llm": run_free_llm,
}
