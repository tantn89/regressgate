# GitHub Action

```yaml
name: eval-gate
on: pull_request

permissions:
  contents: read
  pull-requests: write          # for the PR comment

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e .       # your application
      - uses: tantn89/regressgate@v0.1.0
        with:
          config: regressgate.yaml
          baseline: evals/baseline.json
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

## Inputs and outputs

| Input | Default | Meaning |
|---|---|---|
| `baseline` | required | Baseline report to compare against |
| `config` | `regressgate.yaml` | Suite config |
| `report` | `.regressgate/report.json` | Where the new report is written |
| `repeats` | from the config | Trials per case |
| `install` | `regressgate` | pip requirement used to install regressgate |
| `comment` | `true` | Post or update one PR comment with the verdict |
| `github-token` | `github.token` | Token for the comment |

Outputs: `verdict` (`pass`, `improvement`, `warn`, `regression`) and `failed`
(`"true"` or `"false"`). The step fails on a regression, so the check turns red.

The verdict and the run summary go to the job summary. On pull requests the action keeps a
single comment up to date instead of adding one per push.

## Where the baseline lives

**Commit it.** A baseline file in the repository makes "accept the new behaviour" an
explicit, reviewed change: re-run the suite, commit the new baseline in the same pull
request, and the diff shows exactly which cases moved. Downloading the latest artifact
from the default branch also works (the input is just a file path), but it silently moves
the bar whenever main changes.

## Controlling cost

Live evals spend money on every run. Common patterns:

- run on `workflow_dispatch`, or on pull requests with a label (`types: [labeled]` plus an
  `if:` on the label name);
- set `max_mean_cost_usd` so an accidental switch to a more expensive model fails loudly;
- keep the suite small and the repeats at 3-5; see [choosing repeats](statistics.md#choosing-repeats).

[filings-copilot](https://github.com/tantn89/filings-copilot/blob/main/.github/workflows/eval-gate.yml)
uses the label pattern for its agent evals.
