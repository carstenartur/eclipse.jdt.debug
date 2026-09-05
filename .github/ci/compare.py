#!/usr/bin/env python3
"""Compare raw results without equating a different failure with baseline failure."""
import argparse
import json
import os
from pathlib import Path
import sys


def compare(root, expected, result_name='result.json'):
    results = {}
    missing = []
    for cell in expected['include']:
        name = cell['variant']
        folder = root / ('evidence-' + name)
        path = folder / result_name
        if not path.exists():
            missing.append(name)
            continue
        result = json.loads(path.read_text())
        deps = folder / 'external-dependency-hashes.json'
        results[name] = {'result': result, 'dependencies': json.loads(deps.read_text()) if deps.exists() else {}}
    base = results.get('base')
    differences = {}
    for name, entry in results.items():
        if name == 'base' or base is None:
            continue
        key = lambda failure: failure['report'] + '::' + failure['test']
        old = {key(f) for f in base['result']['failures']}
        new = {key(f) for f in entry['result']['failures']}
        common = set(base['dependencies']) & set(entry['dependencies'])
        changed = sorted(k for k in common if base['dependencies'][k] != entry['dependencies'][k])
        missing_deps = sorted(set(base['dependencies']) ^ set(entry['dependencies']))
        differences[name] = {'additional_failing_tests': sorted(new - old),
            'no_longer_failing_tests': sorted(old - new),
            'same_test_failing_in_both': sorted(old & new),
            'changed_external_artifacts': changed, 'different_dependency_inventory': missing_deps,
            'dependency_bytes_match': bool(common) and not changed and not missing_deps,
            'note': 'Matching test names alone do not establish matching causes. Compare traces and test coverage.'}
    return {'result_file': result_name, 'missing_variants': missing, 'comparison': differences,
            'results': {k: {p: v['result'][p] for p in ('ok', 'tests', 'passed', 'skipped', 'build_exit_codes', 'missing_test_modules')}
                        for k, v in results.items()},
            'tests_only_note': 'Core tests-only intentionally exercises the unfixed implementation; its raw failures are retained, not converted into passes.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--reanalyzed', action='store_true', help='Use reanalyzed-result.json; never fall back to raw verdicts')
    args = parser.parse_args()
    root = args.root
    result = compare(root, json.loads(os.environ['EXPECTED_MATRIX']),
                     'reanalyzed-result.json' if args.reanalyzed else 'result.json')
    root.mkdir(parents=True, exist_ok=True)
    (root / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    text = '## Controlled comparison\n\n```json\n' + json.dumps(result, indent=2) + '\n```\n'
    print(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
            out.write(text)
    sys.exit(1 if result['missing_variants'] else 0)
