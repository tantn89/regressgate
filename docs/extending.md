# Custom checks and targets

## Targets

### Python function

`target: package.module:function` (importable from the working directory) or
`target: path/to/file.py:function` (relative to the config file). The function receives the
case `input` and returns one of:

- a string: the output;
- a dict with `output` and any of `citations`, `retrieved`, `input_tokens`,
  `output_tokens`, `cost_usd`; other keys are kept as trial `metadata`;
- a `regressgate.TargetResult`.

An exception fails that trial and is recorded in the report (`error`), so one timeout does
not lose the whole run. Trials run in a thread pool (`concurrency`, default 4); make the
function thread-safe or set `concurrency: 1`.

### HTTP endpoint

`target: https://api.example.com/ask` with `pip install "regressgate[http]"`:

```yaml
target: https://api.example.com/ask
http:
  method: POST
  input_field: question              # request body: {"question": <case input>}
  headers:
    Authorization: Bearer ${API_TOKEN}   # expanded from the environment
  timeout_s: 120
  output_path: data.answer           # dotted paths into the JSON response
  citations_path: data.sources
  cost_path: usage.cost_usd
```

A referenced environment variable that is not set stops the run before the first request.
Header values never reach the report.

## Custom checks

Register a function that takes the target result and the check's parameters:

```python
import json
from regressgate import CheckOutcome, TargetResult, check
from regressgate.checks import CheckConfigError

@check("json_field")
def json_field(result: TargetResult, params: dict) -> CheckOutcome:
    if "field" not in params:
        raise CheckConfigError("missing required param 'field'")
    try:
        data = json.loads(result.output)
    except ValueError as e:
        return CheckOutcome(False, detail=f"not JSON: {e}")
    return CheckOutcome(params["field"] in data, detail="" if params["field"] in data else "absent")
```

```json
{"id": "structured", "input": "...", "checks": [{"type": "json_field", "field": "order_id"}]}
```

- Return `CheckOutcome(passed, score=None, detail="")`. `score` is an optional graded value
  in [0, 1] whose mean is reported per check type.
- Raise `CheckConfigError` for invalid parameters: the run stops with the case and check
  named, instead of scoring every trial as failed.

To use a check from the CLI, it must be registered before the run. Either import its module
from your target module, or publish it in a package through the `regressgate.checks`
entry-point group:

```toml
[project.entry-points."regressgate.checks"]
json_field = "my_checks:json_field"
```

## Using the library directly

```python
from regressgate import GateConfig, compare_reports, load_cases, run_suite

cases = load_cases("cases.jsonl")
head = run_suite(cases, my_target, repeats=5)
result = compare_reports(baseline_report, head, GateConfig(alpha=0.05))
print(result.verdict, result.delta, result.p_worse)
```
