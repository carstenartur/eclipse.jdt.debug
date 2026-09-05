# Report accounting and evidence-only replay

`parity.py` counts serialized `<testcase>` executions, not just the `tests`
attribute of a suite. JDT/Tycho reports can contain many more executions than
that attribute declares. For example, artifacts from Core run `33978411916`
contain 74,314 compiler regression cases in a report whose header says 45.
Debug run `33978370233` has the same kind of discrepancy in `AutomatedSuite`.
These are execution counts, not necessarily distinct Java test methods.

Every suite, including nested suites, is audited in `suite_counts`. Parent and
child counters are not summed. An undercount is retained in `warnings`; a
counter larger than the matching serialized data is an error, because evidence
may be missing. Actual failures, errors and rerun/flaky failure records always
fail, even when their header counters say zero. Malformed XML/counters, suite
errors outside a testcase, missing or skipped-only required modules, incomplete
build phases, nonzero exit codes, `TIMEOUT` and `HARNESS_ERROR` also fail.
A passing Maven exit code alone cannot override XML failures.

## Reanalyze an existing artifact without rebuilding

Use Python 3.11 or newer and extract each original `evidence-*` artifact into its
own directory, retaining `result.json`, `source.json`, `reports/` and markers.
For example, from the diagnostic harness checkout:

```sh
python3 .github/ci/parity.py reanalyze --project debug --evidence evidence-base
```

This writes **only** `reanalyzed-result.json`. The original `result.json`, XML
reports and logs are not rewritten. The replay records the SHA-256 of the
original result and the analyzer, validates the archived project and build
exit codes, and exits nonzero for a failed or incomplete result. The old
GitHub Actions job conclusion is historical and is not changed by replay.

To compare reanalyzed variants, place them under `comparison/evidence-base`,
`comparison/evidence-pr990`, etc. Use a separate comparison directory for Core:

```sh
export EXPECTED_MATRIX="$(python3 .github/ci/parity.py matrix --project debug --diagnostics)"
python3 .github/ci/compare.py comparison --reanalyzed
```

The flag selects `reanalyzed-result.json` explicitly. Missing replay output
is reported as a missing variant; it never silently falls back to the old
verdict. Dependency drift remains visible, and matching failure names do not
prove matching causes. A comparison report is not itself a replacement for
the individual build/test gates.

## Checks

```sh
python3 -m unittest discover -s .github/ci -p 'test_*.py' -v
```

The regression tests include undercounted, nested, incomplete and malformed
reports; empty/skipped modules; hidden failures; build errors and timeouts;
non-destructive CLI replay; and explicit selection of replayed comparisons.
The analyzer repair does not change product code, assertions, retries, test
timeouts, selected source revisions or Java runtimes.
