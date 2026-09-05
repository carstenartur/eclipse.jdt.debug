"""Regression tests for JDT/Tycho report counters and evidence-only replay."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import parity
import compare


class ReportCounterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reports = self.root / 'reports'
        self.module = 'org.eclipse.jdt.debug.tests'
        self.other = 'org.eclipse.jdt.debug.jdi.tests'
        for module in (self.module, self.other):
            self.report(module, '<testsuite tests="1"><testcase name="ok"/></testsuite>')

    def report(self, module, xml):
        path = self.reports / module / 'target/surefire-reports/TEST-example.xml'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(xml)
        return path

    def analyze(self):
        return parity.analyze(self.reports, 'debug')

    def metadata(self, codes=None, project='debug'):
        (self.root / 'result.json').write_text(json.dumps({'ok': False,
            'errors': ['old counter mismatch'], 'build_exit_codes': [0] if codes is None else codes}))
        (self.root / 'source.json').write_text(json.dumps({'project': project, 'variant': 'base'}))

    def test_flat_undercount_is_auditable_warning(self):
        self.report(self.module, '<testsuite name="dynamic" tests="1">'
                    '<testcase name="one"/><testcase name="two"/></testsuite>')
        result = self.analyze()
        self.assertTrue(result['ok'])
        self.assertEqual(result['tests'], 3)
        self.assertEqual(len(result['warnings']), 1)
        count = next(c for c in result['suite_counts'] if c['suite'] == 'dynamic')
        self.assertEqual(count['declared']['tests'], 1)
        self.assertEqual(count['serialized']['tests'], 2)

    def test_realistic_large_suite_undercount(self):
        self.report(self.module, '<testsuite tests="45">' +
                    ''.join('<testcase name="t' + str(i) + '"/>' for i in range(74314)) + '</testsuite>')
        result = self.analyze()
        self.assertTrue(result['ok'])
        self.assertEqual(result['tests'], 74315)

    def test_declared_count_larger_than_cases_is_error(self):
        self.report(self.module, '<testsuite tests="2"><testcase name="one"/></testsuite>')
        result = self.analyze()
        self.assertFalse(result['ok'])
        self.assertIn('declared=2, serialized=1', result['errors'][0])

    def test_nested_counts_do_not_double_count_executions(self):
        self.report(self.module, '<testsuites tests="2"><testsuite tests="1"><testcase name="a"/>'
                    '</testsuite><testsuite tests="1"><testcase name="b"/></testsuite></testsuites>')
        result = self.analyze()
        self.assertTrue(result['ok'])
        self.assertEqual(result['tests'], 3)
        self.assertEqual(result['warnings'], [])

    def test_nested_suite_missing_cases_cannot_hide_in_parent(self):
        self.report(self.module, '<testsuites><testsuite tests="2"><testcase name="a"/>'
                    '</testsuite></testsuites>')
        self.assertFalse(self.analyze()['ok'])

    def test_nested_declared_failure_without_details_is_error(self):
        self.report(self.module, '<testsuites><testsuite failures="1"><testcase name="a"/>'
                    '</testsuite></testsuites>')
        self.assertFalse(self.analyze()['ok'])

    def test_testsuite_can_contain_nested_suites(self):
        self.report(self.module, '<testsuite tests="1"><testsuite tests="1"><testcase name="a"/>'
                    '</testsuite></testsuite>')
        self.assertTrue(self.analyze()['ok'])
        self.assertEqual(self.analyze()['tests'], 2)

    def test_failure_and_error_counters_are_separate(self):
        self.report(self.module, '<testsuite failures="1" errors="0"><testcase name="a">'
                    '<error>setup</error></testcase></testsuite>')
        result = self.analyze()
        self.assertFalse(result['ok'])
        self.assertTrue(result['errors'])
        self.assertEqual(result['failures'][0]['kind'], 'error')

    def test_actual_failures_fail_even_with_zero_header_counts(self):
        for tag in ('failure', 'error', 'flakyFailure', 'flakyError', 'rerunFailure', 'rerunError'):
            with self.subTest(tag=tag):
                self.report(self.module, '<testsuite tests="0" failures="0" errors="0"><testcase name="a">'
                            '<' + tag + ' message="bad">trace</' + tag + '></testcase></testsuite>')
                result = self.analyze()
                self.assertFalse(result['ok'])
                self.assertEqual(result['failures'][0]['trace'], 'trace')
                self.assertEqual(result['failures'][0]['kind'], tag)

    def test_suite_failure_outside_testcase_is_not_lost(self):
        self.report(self.module, '<testsuite tests="1"><error message="setup"/>'
                    '<testcase name="a"/></testsuite>')
        self.assertFalse(self.analyze()['ok'])

    def test_suite_flakes_header_alone_fails(self):
        self.report(self.module, '<testsuite tests="1" flakes="1"><testcase name="a"/></testsuite>')
        self.assertFalse(self.analyze()['ok'])

    def test_empty_required_module_cannot_pass(self):
        self.report(self.module, '<testsuite tests="0"/>')
        result = self.analyze()
        self.assertFalse(result['ok'])
        self.assertEqual(result['missing_test_modules'], [self.module])

    def test_skipped_only_required_module_cannot_pass(self):
        self.report(self.module, '<testsuite tests="1" skipped="1"><testcase name="a">'
                    '<skipped/></testcase></testsuite>')
        result = self.analyze()
        self.assertFalse(result['ok'])
        self.assertEqual(result['missing_test_modules'], [self.module])

    def test_missing_skip_details_are_error(self):
        self.report(self.module, '<testsuite tests="1" skipped="1"><testcase name="a"/></testsuite>')
        self.assertFalse(self.analyze()['ok'])

    def test_case_with_skip_and_failure_counts_once_as_failure(self):
        self.report(self.module, '<testsuite><testcase name="a"><skipped/><failure/></testcase></testsuite>')
        result = self.analyze()
        self.assertFalse(result['ok'])
        self.assertEqual(result['passed'], 1)
        self.assertEqual(result['skipped'], 0)
        self.assertEqual(len(result['failures']), 1)

    def test_invalid_counters_fail_closed(self):
        for attribute in ('tests', 'failures', 'errors', 'skipped', 'flakes'):
            for value in ('-1', 'bad', '1.5', ''):
                with self.subTest(attribute=attribute, value=value):
                    self.report(self.module, '<testsuite ' + attribute + '="' + value + '">'
                                '<testcase name="a"/></testsuite>')
                    self.assertFalse(self.analyze()['ok'])

    def test_truncated_xml_fails(self):
        self.report(self.module, '<testsuite><testcase name="a"/>')
        self.assertFalse(self.analyze()['ok'])

    def test_unexpected_root_fails(self):
        self.report(self.module, '<notJUnit><testcase name="a"/></notJUnit>')
        self.assertFalse(self.analyze()['ok'])

    def test_replay_uses_raw_xml_not_obsolete_verdict(self):
        self.metadata()
        before = (self.root / 'result.json').read_bytes()
        result = parity.reanalyze(self.root, 'debug')
        self.assertTrue(result['ok'])
        self.assertEqual(result['original_result_sha256'], hashlib.sha256(before).hexdigest())
        self.assertEqual((self.root / 'result.json').read_bytes(), before)

    def test_failed_missing_or_invalid_build_exit_codes_stay_red(self):
        for codes in ([1], [124], [], [0, 0], ['0'], [False], 0):
            with self.subTest(codes=codes):
                self.metadata(codes)
                self.assertFalse(parity.reanalyze(self.root, 'debug')['ok'])

    def test_missing_exit_code_key_fails(self):
        self.metadata()
        (self.root / 'result.json').write_text('{}')
        self.assertFalse(parity.reanalyze(self.root, 'debug')['ok'])

    def test_core_requires_both_build_phases(self):
        result = {'ok': True, 'errors': []}
        parity.validate_build(result, [0], self.root, 'core')
        self.assertFalse(result['ok'])
        result = {'ok': True, 'errors': []}
        parity.validate_build(result, [0, 0], self.root, 'core')
        self.assertTrue(result['ok'])

    def test_timeout_and_harness_markers_cannot_be_hidden(self):
        for marker in ('TIMEOUT', 'HARNESS_ERROR'):
            with self.subTest(marker=marker):
                self.metadata()
                path = self.root / marker
                path.touch()
                self.assertFalse(parity.reanalyze(self.root, 'debug')['ok'])
                path.unlink()

    def test_project_mismatch_fails(self):
        self.metadata(project='core')
        self.assertFalse(parity.reanalyze(self.root, 'debug')['ok'])

    def test_missing_and_malformed_metadata_fail(self):
        for name in ('source.json', 'result.json'):
            for contents in (None, '{broken', '[]', 'null'):
                with self.subTest(name=name, contents=contents):
                    self.metadata()
                    path = self.root / name
                    if contents is None:
                        path.unlink()
                    else:
                        path.write_text(contents)
                    self.assertFalse(parity.reanalyze(self.root, 'debug')['ok'])

    def test_cli_preserves_inputs_and_sets_exit_status(self):
        self.metadata()
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        command = [sys.executable, str(Path(parity.__file__).resolve()), 'reanalyze',
                   '--project', 'debug', '--evidence', str(self.root)]
        run = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(json.loads((self.root / 'reanalyzed-result.json').read_text())['ok'])
        self.assertEqual(before, {name: Path(name).read_bytes() for name in before})
        self.report(self.module, '<testsuite><testcase name="a"><failure/></testcase></testsuite>')
        run = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertFalse(json.loads((self.root / 'reanalyzed-result.json').read_text())['ok'])


    def test_comparison_uses_explicitly_selected_reanalysis(self):
        folder = self.root / 'evidence-base'
        folder.mkdir()
        self.metadata()
        result = parity.reanalyze(self.root, 'debug')
        (folder / 'reanalyzed-result.json').write_text(json.dumps(result))
        raw = dict(result, ok=False)
        (folder / 'result.json').write_text(json.dumps(raw))
        expected = {'include': [{'variant': 'base'}]}
        self.assertFalse(compare.compare(self.root, expected)['results']['base']['ok'])
        selected = compare.compare(self.root, expected, 'reanalyzed-result.json')
        self.assertTrue(selected['results']['base']['ok'])
        self.assertEqual(selected['result_file'], 'reanalyzed-result.json')

    def test_comparison_does_not_fall_back_to_obsolete_result(self):
        folder = self.root / 'evidence-base'
        folder.mkdir()
        (folder / 'result.json').write_text('{}')
        result = compare.compare(self.root, {'include': [{'variant': 'base'}]}, 'reanalyzed-result.json')
        self.assertEqual(result['missing_variants'], ['base'])


if __name__ == '__main__':
    unittest.main()
