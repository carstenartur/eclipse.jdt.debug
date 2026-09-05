import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import parity
import compare


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def report(self, module, body, attrs='tests="1" failures="0" errors="0"'):
        folder = self.root / module / 'target/surefire-reports'
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'TEST-example.xml').write_text('<testsuite ' + attrs + '>' + body + '</testsuite>')

    def pair(self, case='<testcase classname="Example" name="testOne"/>'):
        for name in ('org.eclipse.jdt.debug.tests', 'org.eclipse.jdt.debug.jdi.tests'):
            self.report(name, case)

    def test_missing_reports_fail(self):
        self.assertFalse(parity.analyze(self.root, 'debug')['ok'])

    def test_both_required_modules_pass(self):
        self.pair()
        result = parity.analyze(self.root, 'debug')
        self.assertTrue(result['ok'])
        self.assertEqual(result['passed'], 2)

    def test_partial_module_run_fails(self):
        self.report('org.eclipse.jdt.debug.jdi.tests', '<testcase name="one"/>')
        self.assertFalse(parity.analyze(self.root, 'debug')['ok'])

    def test_failure_cannot_be_hidden_by_maven_ignore(self):
        self.pair('<testcase classname="E" name="one"><failure message="bad">trace</failure></testcase>')
        result = parity.analyze(self.root, 'debug')
        self.assertFalse(result['ok'])
        self.assertEqual(len(result['failures']), 2)

    def test_errors_are_failures(self):
        self.pair('<testcase name="one"><error message="setup">trace</error></testcase>')
        self.assertFalse(parity.analyze(self.root, 'debug')['ok'])

    def test_all_skipped_is_not_success(self):
        self.pair('<testcase name="one"><skipped/></testcase>')
        self.assertFalse(parity.analyze(self.root, 'debug')['ok'])

    def test_declared_failure_without_details_fails(self):
        self.pair()
        self.report('org.eclipse.jdt.debug.tests', '<testcase name="one"/>', 'tests="1" errors="1"')
        self.assertFalse(parity.analyze(self.root, 'debug')['ok'])

    def test_incomplete_serialized_cases_fail(self):
        self.pair()
        self.report('org.eclipse.jdt.debug.tests', '<testcase name="one"/>', 'tests="2"')
        self.assertFalse(parity.analyze(self.root, 'debug')['ok'])

    def test_malformed_xml_fails(self):
        self.pair('<testcase>')
        self.assertTrue(parity.analyze(self.root, 'debug')['errors'])

    def test_core_matrix_is_pinned_and_separated(self):
        cells = parity.matrix('core', True, 'ignored')
        self.assertEqual([c['variant'] for c in cells], ['base', 'product-only', 'tests-only', 'full'])
        self.assertTrue(all(len(c['ref']) == 40 for c in cells))

    def test_debug_matrix_is_pinned(self):
        self.assertEqual([c['variant'] for c in parity.matrix('debug', True, 'ignored')], ['base', 'pr990', 'pr992'])

    def test_regular_build_does_not_select_diagnostic_refs(self):
        self.assertEqual(parity.matrix('core', False, 'abc'), [{'variant': 'current', 'ref': 'abc'}])

    def test_wrong_checkout_rejected_before_any_patch(self):
        with patch.object(parity, 'call', return_value='wrong\n'):
            with self.assertRaises(RuntimeError):
                parity.prepare_source(self.root, 'core', 'base', self.root)

    def test_hung_process_is_bounded_and_red(self):
        import sys
        with patch.object(parity, 'snapshot'):
            result = parity.bounded_build([sys.executable, '-c', 'import time; time.sleep(60)'],
                self.root, self.root, 'timeout-test', time.monotonic() - 1)
        self.assertEqual(result, 124)
        self.assertTrue((self.root / 'TIMEOUT').exists())

    def test_missing_comparison_variant_is_explicit(self):
        result = compare.compare(self.root, {'include': [{'variant': 'base', 'ref': parity.DEBUG_BASE}]})
        self.assertEqual(result['missing_variants'], ['base'])


if __name__ == '__main__':
    unittest.main()
