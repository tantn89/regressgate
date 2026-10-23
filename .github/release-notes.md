First release of regressgate: fail CI on real LLM, RAG and agent eval regressions, not on noise.

```bash
pip install regressgate
```

## Highlights

- **Deterministic checks**: contains, lead, equals, regex, forbidden, abstain, number (with
  scale words and units), citation and retrieval (recall@k, MRR); custom checks through a
  decorator or the `regressgate.checks` entry-point group.
- **Repeated trials** against a Python function or an HTTP endpoint, with cost, latency and
  per-trial errors in a versioned JSON report.
- **Statistical gate**: a stratified permutation test for broad drops plus Tarone-corrected
  Fisher exact tests for single broken cases, each at alpha / 2; `warn` for drops within
  noise; hard limits for pass rate, cost and p95 latency.
- **GitHub Action** with job summary, a single updated PR comment, and `verdict` / `failed`
  outputs.

In a simulation of a 20-case suite with typical noise, a "fail on any drop" gate fails
35-48% of unchanged pull requests; regressgate stays at or below 2%, and with five trials
per case catches a single broken case 92% of the time.

Docs: https://tantn89.github.io/regressgate/
