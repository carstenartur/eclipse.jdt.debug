# Fork CI diagnosis

Fork-only CI, not an upstream product change. `maven.yml` now runs the full Jenkins-style build. `jenkins-parity.yml` is shared with the Core fork; cross-repository callers pin the workflow and `harness_ref` to the same full commit SHA.

## Controlled comparisons

Run **Jenkins parity and controlled diagnosis** with `diagnostics=true` to compare the fixed commits in `parity.py`. Debug compares the base and PRs 990/992. Core compares the base, product-only, tests-only and full PR 5364. Patches and probes exist only in disposable checkouts. Existing PR branches are not updated.

All variants receive the same verified archive: Temurin 26 build 34 for Maven/tests; actual Temurin 8.0.482+8, 11.0.30+7, 17.0.18+8 and 21.0.10+7 for BREE libraries; Maven 3.9.11; a frozen parent POM snapshot. Main/test VM remains Java 26. Historical versions are for reproducing the observed CI configuration, not recommendations for deploying current applications.

Source checkouts include full Git history for Tycho/JGit qualifiers. Before building, a preflight checks source history and the toolchains required by reactor manifests. The Maven repository ID is deliberately different from the inherited `eclipse` p2 repository ID, so settings cannot replace that target-platform source.

Core bootstraps ECJ version 99.99 before running its original compliance set and p2/API/Javadoc profiles. Debug uses the Java 26/BREE/API/Javadoc profiles. Build deadlines remain 90 and 40 minutes; bounded evidence collection follows a timeout. All checks, assertions, VM connection timeouts and retry/port behavior remain unchanged.

## Evidence and limitations

The exact Jenkins JDK distribution could not be downloaded: **Temurin 26-beta+34-ea is not byte-identical to Jenkins' OpenJDK 26-ea+34**. Exact Jenkins Maven/BREE patch versions and agent hardware were not obtained. GitHub Ubuntu 24.04 and Xvfb differ from Eclipse's agents and Xvnc. Every evidence artifact records these differences. Other p2/SNAPSHOT dependencies are hash-compared, not fully frozen; do not attribute results solely to code if dependencies or coverage differ.

`tool-evidence` contains checksums, versions and the parent snapshot. Each `evidence-*` contains source SHAs/patches, exact commands, Maven logs, XML reports, workspace logs, process/port/cgroup snapshots and bounded thread dumps for stalls/deadlines. A shared debug probe captures target PID, liveness, exit code and socket state immediately after attach failure, before cleanup. Existing JDI readers capture child stdout/stderr; no competing pipe consumer is added.

`comparison` lists added/removed failing test identities and dependency differences. Matching test names alone do not prove matching root causes. Inspect traces. Maven's failure-ignore flag matches Jenkins collection behavior, but the final XML/exit-code gate rejects real failures, malformed/incomplete reports, missing required modules, timeouts and all-skipped runs. Core's tests-only cell intentionally tests unfixed code; its regression failures stay red.

## QA

`python3 -m unittest discover -s .github/ci -p 'test_*.py' -v`

19 harness tests cover report integrity, partial/missing tests, fixed source variants, real child-process timeout, missing comparison cells, shallow history, missing/present BREE installations and non-colliding repository IDs. The initial setup runs exposed missing BREE JDKs and an overlapping repository ID before any JDT tests executed; those are harness setup failures, not evidence explaining the original upstream test failures.
