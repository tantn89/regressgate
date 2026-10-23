# Getting started

## Install

```bash
pip install regressgate             # Python 3.10+
pip install "regressgate[http]"     # to call an HTTP endpoint as the target
```

## 1. Write a target

A target is the system under test. The simplest is a Python function that takes a case's
`input` and returns the output text:

```python
# my_app/eval_target.py
from my_app import answer_question

def answer(question: str) -> dict:
    result = answer_question(question)
    return {
        "output": result.text,
        "citations": [{"doc": s.doc_id} for s in result.sources],  # for `citation` checks
        "cost_usd": result.cost,                                      # for cost budgets
    }
```

Returning a plain string is enough when you only check the text. See
[targets](extending.md#targets) for HTTP endpoints and every field a target can report.

## 2. Write cases

One JSON object per line in `cases.jsonl` (YAML lists work too):

```json
{"id": "refund-window", "input": "Can I get a refund?", "checks": [{"type": "contains", "terms": ["30 days"]}]}
{"id": "unknown", "input": "Do you accept Dogecoin?", "checks": [{"type": "abstain"}]}
```

Every check in a case must pass for a trial to pass. All check types are listed in
[cases and checks](cases-and-checks.md).

## 3. Configure the suite

```yaml
# regressgate.yaml
target: my_app/eval_target.py:answer
cases: cases.jsonl
repeats: 5
```

Paths in the file are relative to the file itself, so the suite runs the same from any
directory.

## 4. Run and gate

```bash
regressgate run --out baseline.json
# ... change the prompt, the model, the retriever ...
regressgate run --out head.json
regressgate compare baseline.json head.json
```

`run` prints a summary: pass rate, the range it would land in on a re-run, flaky cases,
latency, cost, per-check pass rates and why failing cases failed. `compare` prints a
verdict and exits with:

| Exit code | Meaning |
|---|---|
| 0 | `pass`, `improvement` or `warn` (a drop that is within noise) |
| 1 | `regression`, or a hard limit exceeded |
| 2 | usage or configuration error |

## Try it without writing anything

The repository ships an offline example with a deliberately flaky case:

```bash
git clone https://github.com/tantn89/regressgate && cd regressgate
pip install -e .
regressgate run -c examples/support_bot/regressgate.yaml --out head.json
regressgate compare examples/support_bot/baseline.json head.json -c examples/support_bot/regressgate.yaml
SUPPORT_BOT_VARIANT=broken regressgate run -c examples/support_bot/regressgate.yaml --out broken.json
regressgate compare examples/support_bot/baseline.json broken.json -c examples/support_bot/regressgate.yaml
```

The first comparison passes or warns; the second is a regression.
