#!/usr/bin/env python3
"""Validate the missing attach deadline in PR 992 before publishing any change."""
import collections
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

BASE = '2dfead1ad5674407e6d9d53026decfcc9d5fdf04'
ROOT = Path('source')
PACKAGE = Path('org.eclipse.jdt.debug.jdi.tests/tests/org/eclipse/debug/jdi/tests')
EVIDENCE = Path('evidence')
TEST = r'''/*******************************************************************************
 * Copyright (c) 2026 contributors to the Eclipse Foundation.
 *
 * This program and the accompanying materials
 * are made available under the terms of the Eclipse Public License 2.0
 * which accompanies this distribution, and is available at
 * https://www.eclipse.org/legal/epl-2.0/
 *
 * SPDX-License-Identifier: EPL-2.0
 *******************************************************************************/
package org.eclipse.debug.jdi.tests;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import junit.framework.TestCase;

/** Tests the deadline and subsequent cleanup with the real JDI connector. */
public class VMConnectionTimeoutTest extends TestCase {

	public void testPeerThatDoesNotCompleteHandshakeCannotBlockStartup() throws Exception {
		assertSilentPeerIsBounded(false);
	}

	public void testHandshakeTimeoutReachesCleanupAndRetainsDiagnostics() throws Exception {
		assertSilentPeerIsBounded(true);
	}

	private void assertSilentPeerIsBounded(boolean throughStartup) throws Exception {
		int previousPort = AbstractJDITest.fBackEndPort;
		ConnectionProbe probe = new ConnectionProbe();
		FutureTask<Void> attempt = new FutureTask<>(() -> {
			if (throughStartup) {
				probe.launchTargetAndConnectToVM();
			} else {
				probe.connectToVM();
			}
			return null;
		});
		Thread connecting = new Thread(attempt, "JDI startup timeout test");
		connecting.setDaemon(true);
		try (ServerSocket listener = new ServerSocket(0)) {
			listener.setSoTimeout(10000);
			AbstractJDITest.fBackEndPort = listener.getLocalPort();
			connecting.start();
			try (Socket peer = listener.accept()) {
				peer.setSoTimeout(10000);
				assertEquals("JDWP-Handshake", new String(peer.getInputStream().readNBytes(14), StandardCharsets.US_ASCII));
				// Keep the connection open without answering its JDWP handshake.
				try {
					attempt.get(10, TimeUnit.SECONDS);
					fail("A peer without a JDWP handshake must not be accepted as a VM");
				} catch (ExecutionException expected) {
					Throwable failure = expected.getCause();
					assertTrue("Startup must report its ordinary connection failure: " + failure, failure instanceof Error);
					assertEquals("Could not contact the VM", failure.getMessage());
					assertTrue("Retain the transport timeout as the cause", failure.getCause() instanceof org.eclipse.jdi.TimeoutException);
					assertTrue("Record the process state before cleanup, not after destroying it",
							Arrays.stream(failure.getSuppressed()).anyMatch(detail -> detail.getMessage() != null
									&& detail.getMessage().contains("pid=42, alive=true")
									&& detail.getMessage().contains("localhost:" + listener.getLocalPort())));
					if (throughStartup) {
						assertFalse("Cleanup must terminate the owned process", probe.process.isAlive());
						assertNull("Cleanup must clear the target handle", probe.fLaunchedVM);
						assertNull(probe.fConsoleReader);
						assertNull(probe.fConsoleErrorReader);
					}
				} catch (TimeoutException expected) {
					fail("The connector blocked past the startup deadline on a silent peer");
				}
			}
		} finally {
			// Closing the peer releases even the unfixed implementation.
			try {
				connecting.join(10000);
				assertFalse("Startup thread did not terminate after the peer closed", connecting.isAlive());
			} finally {
				probe.stopConsoleTestReaders();
				probe.process.destroy();
				AbstractJDITest.fBackEndPort = previousPort;
			}
		}
	}

	private static final class ConnectionProbe extends AbstractJDITest {
		final Process process = new StreamOnlyProcess();

		ConnectionProbe() {
			fLaunchedVM = process;
		}

		@Override
		protected void launchTarget() {
			// Only the process is substituted; attach uses the real transport.
		}

		@Override
		public void localSetUp() {
			// No target program is needed for a transport-level startup failure.
		}

		void stopConsoleTestReaders() {
			if (fConsoleReader != null) {
				fConsoleReader.stop();
			}
			if (fConsoleErrorReader != null) {
				fConsoleErrorReader.stop();
			}
		}
	}

	private static final class StreamOnlyProcess extends Process {
		private volatile boolean alive = true;

		@Override
		public OutputStream getOutputStream() {
			return OutputStream.nullOutputStream();
		}

		@Override
		public InputStream getInputStream() {
			return InputStream.nullInputStream();
		}

		@Override
		public InputStream getErrorStream() {
			return InputStream.nullInputStream();
		}

		@Override
		public int waitFor() {
			throw new UnsupportedOperationException();
		}

		@Override
		public int exitValue() {
			if (alive) {
				throw new IllegalThreadStateException();
			}
			return 0;
		}

		@Override
		public long pid() {
			return 42;
		}

		@Override
		public void destroy() {
			alive = false;
		}
	}
}
'''


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Source anchor not unique: ' + repr(old))
    return text.replace(old, new)


def apply_fix(text):
    replacements = [
        ('import java.util.Vector;', 'import java.util.Vector;\nimport java.util.concurrent.TimeUnit;'),
        ('import org.eclipse.jdi.Bootstrap;', 'import org.eclipse.jdi.Bootstrap;\nimport org.eclipse.jdi.TimeoutException;'),
        ('// Contact the VM (try at least 10 times for 5 seconds)\n\t\tlong n0 = System.nanoTime();',
         '// Bound each attach as well as the retry loop. A zero connector timeout\n\t\t// waits forever if a peer accepts the socket but does not complete JDWP.\n\t\tlong timeoutNanos = TimeUnit.SECONDS.toNanos(5);\n\t\tThrowable connectionFailure = null;\n\t\tlong n0 = System.nanoTime();'),
        ('\t\t\t\targs.get("hostname").setValue("localhost");\n\n\t\t\t\tfVM = connector.attach(args);',
         '\t\t\t\targs.get("hostname").setValue("localhost");\n\t\t\t\tlong remainingMillis = Math.max(1, TimeUnit.NANOSECONDS.toMillis(timeoutNanos - (System.nanoTime() - n0)));\n\t\t\t\targs.get("timeout").setValue(Long.toString(remainingMillis));\n\n\t\t\t\tfVM = connector.attach(args);'),
        ('\t\t\t} catch (IOException e) {\n\t\t\t\tlong n1 = System.nanoTime();\n\t\t\t\tif (i > 10 && n1 - n0 > 5_000_000_000L) {',
         '\t\t\t} catch (IOException | TimeoutException e) {\n\t\t\t\tconnectionFailure = e;\n\t\t\t\tlong n1 = System.nanoTime();\n\t\t\t\tif (n1 - n0 >= timeoutNanos) {'),
        ('\t\t\tthrow new Error("Could not contact the VM");',
         '\t\t\tError failure = new Error("Could not contact the VM", connectionFailure);\n'
         '\t\t\t// Retain pre-cleanup state in the test failure even when console output\n'
         '\t\t\t// from the target process is missing from the CI test report.\n'
         '\t\t\tfailure.addSuppressed(new IllegalStateException("JDI startup at localhost:" + fBackEndPort\n'
         '\t\t\t\t\t+ "; target " + describeProcess(fLaunchedVM) + "; proxy " + describeProcess(fLaunchedProxy)\n'
         '\t\t\t\t\t+ "; runtime=" + Runtime.version() + "; vendor=" + System.getProperty("java.vendor")));\n'
         '\t\t\tthrow failure;'),
        ('\t/**\n\t * Initializes the fields that are used by this test only.\n\t */',
         '\n\tprivate static String describeProcess(Process process) {\n'
         '\t\tif (process == null) {\n\t\t\treturn "not started";\n\t\t}\n'
         '\t\tString pid;\n\t\ttry {\n\t\t\tpid = Long.toString(process.pid());\n'
         '\t\t} catch (UnsupportedOperationException e) {\n\t\t\tpid = "unavailable";\n\t\t}\n'
         '\t\ttry {\n\t\t\treturn "pid=" + pid + ", alive=false, exitCode=" + process.exitValue();\n'
         '\t\t} catch (IllegalThreadStateException e) {\n\t\t\treturn "pid=" + pid + ", alive=true";\n\t\t}\n\t}\n'
         '\t/**\n\t * Initializes the fields that are used by this test only.\n\t */')]
    for old, new in replacements:
        text = replace_once(text, old, new)
    return text


def read_cases(folder):
    cases = []
    reports = sorted(folder.glob('TEST-*.xml'))
    if not reports:
        raise RuntimeError('No test reports in ' + str(folder))
    for report in reports:
        root = ET.parse(report).getroot()
        if root.tag != 'testsuite':
            raise RuntimeError('Unexpected report root: ' + root.tag)
        report_failures = 0
        for case in root.iter('testcase'):
            failed = [f for f in case if f.tag in ('failure', 'error', 'flakyFailure', 'flakyError', 'rerunFailure', 'rerunError')]
            report_failures += len(failed)
            cases.append({'class': case.get('classname'), 'name': case.get('name'),
                          'time': case.get('time'), 'skipped': case.find('skipped') is not None,
                          'failures': [{'kind': f.tag, 'message': f.get('message'), 'trace': f.text} for f in failed]})
        if int(root.get('tests', '0')) > len(list(root.iter('testcase'))):
            raise RuntimeError('Missing serialized test results in ' + str(report))
        if int(root.get('failures', '0')) + int(root.get('errors', '0')) > report_failures:
            raise RuntimeError('Missing failure details in ' + str(report))
    return cases


def run_phase(phase, selection):
    args = ['mvn', 'clean', 'verify', '-B', '--fail-at-end', '-pl', 'org.eclipse.jdt.debug.jdi.tests', '-am',
            '-Ptest-on-javase-26', '-Pbree-libs', '-Dmaven.repo.local=' + str(Path('.m2/repository').resolve()),
            '-Dmaven.test.failure.ignore=true', '-DtrimStackTrace=false']
    if selection:
        args += ['-Dtest=' + selection, '-DfailIfNoTests=false', '-Dsurefire.failIfNoSpecifiedTests=false']
    (EVIDENCE / (phase + '-command.json')).write_text(json.dumps(args, indent=2) + '\n')
    with (EVIDENCE / (phase + '-maven.log')).open('w') as log:
        completed = subprocess.run(['timeout', '--kill-after=20s', '15m', *args], cwd=ROOT,
                                   stdout=log, stderr=subprocess.STDOUT, check=False)
    (EVIDENCE / (phase + '-exit.txt')).write_text(str(completed.returncode) + '\n')
    dest = EVIDENCE / phase
    shutil.copytree(ROOT / 'org.eclipse.jdt.debug.jdi.tests/target/surefire-reports', dest, dirs_exist_ok=True)
    if completed.returncode:
        raise RuntimeError(phase + ': Maven failed: ' + str(completed.returncode))
    cases = read_cases(dest)
    if any(c['skipped'] for c in cases):
        raise RuntimeError(phase + ': skipped test')
    failed = [c for c in cases if c['failures']]
    if phase == 'before':
        expected = {'testPeerThatDoesNotCompleteHandshakeCannotBlockStartup',
                    'testHandshakeTimeoutReachesCleanupAndRetainsDiagnostics'}
        if len(cases) != 2 or {c['name'] for c in failed} != expected:
            raise RuntimeError('Did not reproduce both intended failures')
        if any(len(c['failures']) != 1 or c['failures'][0]['message'] !=
               'The connector blocked past the startup deadline on a silent peer' for c in failed):
            raise RuntimeError('Unexpected before-fix failure')
    else:
        if failed:
            raise RuntimeError(phase + ': actual test failures: ' + str(failed))
        if phase == 'after' and len(cases) != 17:
            raise RuntimeError('Expected 15 cleanup and 2 deadline regression executions')
        if phase == 'suite':
            original = read_cases(Path('baseline/reports/org.eclipse.jdt.debug.jdi.tests/target/surefire-reports'))
            key = lambda c: (c['class'], c['name'])
            old = collections.Counter(map(key, original))
            new = collections.Counter(map(key, cases))
            additional = collections.Counter({('org.eclipse.debug.jdi.tests.VMConnectionTimeoutTest', n): 1 for n in
                ('testPeerThatDoesNotCompleteHandshakeCannotBlockStartup', 'testHandshakeTimeoutReachesCleanupAndRetainsDiagnostics')})
            if new != old + additional:
                raise RuntimeError('Suite coverage changed unexpectedly: missing=' + str(old - new) + ' extra=' + str(new - old))
    summary = {'phase': phase, 'tests': len(cases), 'failures': len(failed), 'cases': cases,
               'test_source_sha256': hashlib.sha256((ROOT / PACKAGE / 'VMConnectionTimeoutTest.java').read_bytes()).hexdigest()}
    (EVIDENCE / (phase + '-result.json')).write_text(json.dumps(summary, indent=2) + '\n')
    print(phase + ': ' + str(len(cases)) + ' executions, ' + str(len(failed)) + ' failures', flush=True)


def main():
    EVIDENCE.mkdir(exist_ok=True)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if head != BASE:
        raise RuntimeError('Unexpected source revision')
    package = ROOT / PACKAGE
    test_path = package / 'VMConnectionTimeoutTest.java'
    if test_path.exists():
        raise RuntimeError('Refusing to replace an existing test')
    test_path.write_text(TEST)
    run_phase('before', 'org.eclipse.debug.jdi.tests.VMConnectionTimeoutTest')
    path = package / 'AbstractJDITest.java'
    path.write_text(apply_fix(path.read_text()))
    path = package / 'AutomatedSuite.java'
    path.write_text(replace_once(path.read_text(), '\t\taddTest(new TestSuite(VMStartupCleanupTest.class));',
                                '\t\taddTest(new TestSuite(VMConnectionTimeoutTest.class));\n\t\taddTest(new TestSuite(VMStartupCleanupTest.class));'))
    run_phase('after', 'org.eclipse.debug.jdi.tests.VMConnectionTimeoutTest,org.eclipse.debug.jdi.tests.VMStartupCleanupTest')
    run_phase('suite', None)
    subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)
    paths = [str(PACKAGE / name) for name in ('AbstractJDITest.java', 'AutomatedSuite.java', 'VMConnectionTimeoutTest.java')]
    subprocess.run(['git', 'add', '--', *paths], cwd=ROOT, check=True)
    (EVIDENCE / 'candidate.patch').write_bytes(subprocess.check_output(['git', 'diff', '--cached', '--binary'], cwd=ROOT))
    (EVIDENCE / 'base.txt').write_text(BASE + '\n')
    subprocess.run(['git', 'config', 'user.name', 'Carsten Hammer'], cwd=ROOT, check=True)
    subprocess.run(['git', 'config', 'user.email', 'carsten.hammer@t-online.de'], cwd=ROOT, check=True)
    subprocess.run(['git', 'commit', '-s', '-m', 'Bound failed JDI attaches so startup cleanup is reachable', '-m',
                    'Retain the five-second startup budget, apply its remainder to each attach, and retain the transport cause and pre-cleanup process state in the failure. The unchanged silent-peer regressions fail on the prior cleanup-only commit and pass with this change; all 15 existing cleanup tests and the complete JDI suite also pass.'], cwd=ROOT, check=True)
    (EVIDENCE / 'candidate-commit.txt').write_text(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True))


if __name__ == '__main__':
    main()
