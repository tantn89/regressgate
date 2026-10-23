# Cases and checks

## Case format

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Unique, stable name. Reports are compared case by case through it |
| `input` | yes | A string or an object, passed to the target as is |
| `checks` | yes | One or more checks; a trial passes when all of them pass |
| `tags` | no | Labels shown in reports, for example the question type |
| `metadata` | no | Free-form, ignored by regressgate |

Each check has a `type`, optional `name` (its label in reports; repeated types get `#2`,
`#3`) and type-specific parameters. In JSONL files, lines starting with `//` are comments.

!!! tip "Keep ids stable"
    Renaming a case makes it a new case: it is reported as added, and the old one as
    removed, and neither takes part in the comparison.

## Built-in checks

### Text

`contains`
:   All `terms` appear in the output (`mode: any` for at least one). Case-insensitive
    unless `case_sensitive: true`.

`lead`
:   The terms appear in the first `sentences` sentences (default 1). Use it when the answer
    must come first, for example "which company had the highest margin".

`equals`
:   The output equals `value` after collapsing whitespace and lowercasing (both optional).

`regex`
:   `pattern` matches somewhere in the output (case-insensitive).

`forbidden`
:   None of `patterns` match. The natural partner of `abstain`: a refusal that still
    quotes an invented figure fails.

`abstain`
:   The output declines to answer within its first `sentences` sentences (default 2).
    Recognises common refusal phrasings ("I can't tell you", "not in the data", "would be
    a guess"); add domain wording with `extra_phrases` (regular expressions).

### Numbers

`number`
:   A figure in the output is within `rel_tol` (relative) or `abs_tol` (absolute) of
    `value`. Understands thousands separators, decimals, a leading minus, `$`, `%` or
    "percent", and scale words: `$130.5B`, `130,497 million` and `130.5 billion` all match
    130,497,000,000 within 1%. With `unit: "%"` only percentages match, and a percentage
    never satisfies a plain value.

### Sources

`citation`
:   One of the target's `citations` matches one of `any_of`. A citation matches when every
    expected field is equal, so `{"ticker": "NVDA", "section": "7"}` accepts any NVDA
    Item 7 passage.

`retrieval`
:   An item in the target's ranked `retrieved` list matches `any_of` (and, optionally,
    contains all `terms` in its `text`) within the top `k` (default 5). The score is the
    reciprocal rank, so the check's pass rate is recall@k and its mean score is MRR.

## Configuration errors fail fast

An unknown check type or an invalid parameter (a missing `terms`, a bad regex, a `number`
without a tolerance) stops the run before the first target call, with the case id and
check label in the message. It is never scored as a failed trial, because it says nothing
about the system under test.
