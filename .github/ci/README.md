# Fork CI diagnosis

This is fork-only CI, not an upstream product change. `maven.yml` runs the complete Jenkins-style build rather than the former Java 21 packaging job. `jenkins-parity.yml` is also a reusable workflow for the Core fork. Cross-repository callers must pin both the workflow and `harness_ref` to the same full commit SHA.

## Reproduction

Run **Jenkins parity and controlled diagnosis** with `diagnostics=true` to compare the commits recorded in `parity.py`. Debug runs the base and PRs 990/992. Core runs the base, product-only change, tests-only change, and full PR 5364. Changes and diagnostic probes are applied only to disposable checkouts; existing PR branches are not updated.

All cells receive the same verified toolchain archive and frozen parent POM. They use fresh Maven repositories and workspaces. The primary VM is Temurin OpenJDK 26 build 34, matching the feature/build of the observed Jenkins failures. Legacy tests also have Temurin 8.0.482+8; Maven is pinned to 3.9.11. The exact Jenkins JDK distribution was not available from its expired download URL: **Temurin 26-beta+34-ea is not a byte-identical replacement for Jenkins' 26-ea+34 distribution**. GitHub runner hardware/kernel and Xvfb also differ from Eclipse's agents and Xvnc. These limitations are repeated in every artifact.

Core first bootstraps its ECJ with version 99.99, then runs the same compliance set, p2/API/Javadoc profiles and comparator flags as its Jenkinsfile. Debug uses the same Java 26/BREE/API/Javadoc profiles. The build deadlines remain 90 minutes for Core and 40 minutes for Debug; a bounded evidence-collection interval follows a timeout.

## Evidence and interpretation

`tool-evidence` records download checksums, parent snapshot URL, binaries and acknowledged differences. Each `evidence-*` contains source SHAs/patches, exact commands, Maven logs, XML test reports, workspace logs, process/port/cgroup snapshots and bounded thread dumps on a stall/deadline. The existing JDI console readers continue to capture target output; no second pipe consumer is introduced. A common debug-only probe captures process liveness, exit code and Linux socket state immediately after attach fails and before cleanup.

`comparison` reports additional/disappearing failures by test identity. It also compares resolved external artifact hashes: **do not attribute a result solely to a code change when dependencies or test coverage differ**. Other p2/SNAPSHOT artifacts are observed, not fully frozen. Matching failing test names do not prove matching root causes; inspect the full traces.

`maven.test.failure.ignore=true` matches Jenkins's collection behavior, but the post-run XML/exit-code gate always turns real failures, incomplete reports, missing required test modules and timeouts into a failed job. Core's tests-only cell intentionally exercises unfixed code; expected regression-test failures remain visible as failures, never synthetic passes.

## Harness QA

`python3 -m unittest discover -s .github/ci -p 'test_*.py' -v`

The tests cover missing/partial/malformed reports, failures/errors, all-skipped reports, inconsistent counters, exact source matrices, a wrong source checkout, a bounded real child process, and missing comparison cells. Diagnostic changes must not relax production assertions, connection timeouts or retry/port behavior.
