#!/usr/bin/env python3
"""Fork-only CI: controlled source variants, bounded builds, evidence and strict results.

No production source is committed by this helper. Diagnostic probes are applied
only to disposable debug checkouts, identically for all comparison variants.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

CORE_BASE = '8c40c7d2ae12c0a32ab3cca1ab31b53956c65d51'
CORE_HEAD = 'd55a8c72e96ba601562fda02e5698da6323d37e7'
DEBUG_BASE = 'af15c262973bc93c130d33b993c5fd3195ae3ab5'
DEBUG_HEADS = {'pr990': '17bf4ae2fa2388a83430a17662adab17be77a01e',
               'pr992': '2dfead1ad5674407e6d9d53026decfcc9d5fdf04'}
PRODUCT = 'org.eclipse.jdt.core/model/org/eclipse/jdt/internal/core/JavaModelManager.java'
TEST_ROOT = 'org.eclipse.jdt.core.tests.model/src/org/eclipse/jdt/core/tests/model/'
CORE_TESTS = [TEST_ROOT + name for name in ('OptionCacheTests.java', 'AllJavaModelTests.java')]
DEBUG_ROOT = 'org.eclipse.jdt.debug.jdi.tests/tests/org/eclipse/debug/jdi/tests/'


def call(args, cwd=None, timeout=120):
    return subprocess.check_output(args, cwd=cwd, timeout=timeout, text=True,
                                   stderr=subprocess.STDOUT)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def matrix(project, diagnostics, ref):
    if not diagnostics:
        return [{'variant': 'current', 'ref': ref}]
    if project == 'debug':
        return [{'variant': 'base', 'ref': DEBUG_BASE}] + [
            {'variant': key, 'ref': sha} for key, sha in DEBUG_HEADS.items()]
    return [{'variant': key, 'ref': CORE_BASE if key != 'full' else CORE_HEAD}
            for key in ('base', 'product-only', 'tests-only', 'full')]


PROBE = '''package org.eclipse.debug.jdi.tests;

// Fork-only observation: no timeouts, retries, ports or assertions are changed.
final class ForkStartupDiagnostics {
    static void capture(Process process) {
        try { captureImpl(process); } catch (RuntimeException exception) {
            System.err.println("FORK_CI_PROBE_ERROR " + exception);
        }
    }
    private static void captureImpl(Process process) {
        System.err.println("FORK_CI_STARTUP_FAILURE " + java.time.Instant.now());
        if (process != null) {
            System.err.println("pid=" + process.pid() + " alive=" + process.isAlive());
            if (!process.isAlive()) {
                System.err.println("exitCode=" + process.exitValue());
            }
            read("/proc/" + process.pid() + "/status");
            read("/proc/" + process.pid() + "/cgroup");
        }
        read("/etc/hosts");
        read("/proc/net/tcp");
        read("/proc/net/tcp6");
        read("/sys/fs/cgroup/cpu.stat");
        read("/sys/fs/cgroup/memory.events");
    }
    private static void read(String name) {
        try (java.io.InputStream in = java.nio.file.Files.newInputStream(java.nio.file.Path.of(name))) {
            System.err.println(name + "\\n" + new String(in.readNBytes(65536), java.nio.charset.StandardCharsets.UTF_8));
        } catch (Exception exception) {
            System.err.println(name + ": " + exception);
        }
    }
}
'''


def prepare_source(source, project, variant, evidence):
    before = call(['git', 'rev-parse', 'HEAD'], source).strip()
    expected = {v['variant']: v['ref'] for v in matrix(project, True, '')}
    if variant != 'current' and expected.get(variant) != before:
        raise RuntimeError('Checked-out SHA does not match the requested diagnostic variant')
    if project == 'core' and variant in ('product-only', 'tests-only'):
        if before != CORE_BASE:
            raise RuntimeError('Selective variants must start at the pinned Core base')
        call(['git', 'fetch', '--no-tags', 'origin', CORE_HEAD], source)
        paths = [PRODUCT] if variant == 'product-only' else CORE_TESTS
        patch = call(['git', 'diff', CORE_BASE, CORE_HEAD, '--', *paths], source)
        if not patch:
            raise RuntimeError('Empty selective patch')
        patch_file = evidence / 'selected-change.patch'
        patch_file.write_text(patch)
        call(['git', 'apply', '--check', str(patch_file)], source)
        call(['git', 'apply', str(patch_file)], source)
    if project == 'debug' and variant != 'current':
        target = source / (DEBUG_ROOT + 'AbstractJDITest.java')
        text = target.read_text()
        marker = '\t\tif (fVM == null) {\n\t\t\tif (fLaunchedVM != null) {'
        if text.count(marker) != 1:
            raise RuntimeError('Startup probe anchor changed; refusing an ambiguous patch')
        target.write_text(text.replace(marker, '\t\tif (fVM == null) {\n'
            '\t\t\tForkStartupDiagnostics.capture(fLaunchedVM);\n'
            '\t\t\tif (fLaunchedVM != null) {'))
        helper = source / (DEBUG_ROOT + 'ForkStartupDiagnostics.java')
        helper.write_text(PROBE)
        shutil.copy2(helper, evidence / helper.name)
    (evidence / 'effective-source.patch').write_text(call(['git', 'diff', '--binary'], source))
    (evidence / 'source-status.txt').write_text(call(['git', 'status', '--short'], source))
    (evidence / 'Jenkinsfile').write_text((source / 'Jenkinsfile').read_text())
    write_json(evidence / 'source.json', {'project': project, 'variant': variant,
        'checkout_sha': before, 'core_base': CORE_BASE, 'core_head': CORE_HEAD,
        'debug_base': DEBUG_BASE, 'debug_heads': DEBUG_HEADS})


def snapshot(evidence, label, dumps=False):
    path = evidence / 'process-snapshots.log'
    with path.open('a') as out:
        out.write('\n' + dt.datetime.now(dt.timezone.utc).isoformat() + ' ' + label + '\n')
        for command in (['ps', '-eo', 'pid,ppid,pgid,stat,etimes,pcpu,pmem,args'],
                        ['ss', '-ltnp'], ['free', '-m']):
            try:
                out.write(call(command, timeout=5))
            except (OSError, subprocess.SubprocessError) as error:
                out.write(str(error) + '\n')
        for name in ('cpu.stat', 'memory.events', 'memory.current', 'pids.current'):
            try:
                out.write(name + '\n' + Path('/sys/fs/cgroup', name).read_text())
            except OSError:
                pass
    if dumps:
        # A diagnostic attach can itself hang. Bound every dump, and the count.
        try:
            lines = call([str(Path(os.environ['JAVA_HOME'], 'bin/jcmd')), '-l'], timeout=5).splitlines()
        except (OSError, subprocess.SubprocessError):
            return
        for line in lines[:8]:
            pid = line.split(' ', 1)[0]
            if not pid.isdigit() or 'sun.tools.jcmd.JCmd' in line:
                continue
            for cmd in ('VM.command_line', 'Thread.print -l'):
                try:
                    result = call([str(Path(os.environ['JAVA_HOME'], 'bin/jcmd')), pid, *cmd.split()], timeout=5)
                except (OSError, subprocess.SubprocessError) as error:
                    result = str(error)
                with (evidence / ('jvm-' + pid + '.log')).open('a') as out:
                    out.write(result + '\n')


def bounded_build(command, source, evidence, name, deadline):
    log = evidence / (name + '.log')
    (evidence / (name + '-command.json')).write_text(json.dumps(command) + '\n')
    print('RUN ' + ' '.join(command), flush=True)
    with log.open('w') as output:
        process = subprocess.Popen(command, cwd=source, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        last_snapshot = 0.0
        last_size = -1
        last_growth = time.monotonic()
        captured_stall = False
        try:
            while process.poll() is None:
                now = time.monotonic()
                size = log.stat().st_size
                if size != last_size:
                    last_growth, last_size, captured_stall = now, size, False
                if now - last_snapshot > 30:
                    snapshot(evidence, name)
                    last_snapshot = now
                    print(f'{name}: elapsed evidence={size} bytes, process={process.pid}', flush=True)
                if not captured_stall and now - last_growth > 120:
                    snapshot(evidence, name + '-no-output-120s', dumps=True)
                    captured_stall = True
                if now >= deadline:
                    snapshot(evidence, name + '-deadline', dumps=True)
                    (evidence / 'TIMEOUT').write_text(name + '\n')
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=15)
                    return 124
                time.sleep(2)
            return process.returncode
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=15)
            with log.open('rb') as tail:
                tail.seek(max(0, log.stat().st_size - 14000))
                print(tail.read().decode(errors='replace'), flush=True)


def analyze(source, project):
    reports = sorted(source.glob('**/target/surefire-reports/TEST-*.xml'))
    result = {'reports': len(reports), 'tests': 0, 'skipped': 0, 'failures': [],
              'errors': [], 'warnings': [], 'suite_counts': [], 'modules': [], 'cases': []}
    modules, executed_modules = set(), set()
    failure_tags = ('failure', 'error', 'flakyFailure', 'flakyError', 'rerunFailure', 'rerunError')
    for report in reports:
        relative = report.relative_to(source)
        module = relative.parts[0]
        modules.add(module)
        try:
            root = ET.parse(report).getroot()
            if root.tag not in ('testsuite', 'testsuites'):
                raise ValueError('Not a JUnit test report')
            # Inspect each suite separately. Never add parent and child counters:
            # their descendant testcase sets overlap.
            for suite in root.iter():
                if suite.tag not in ('testsuite', 'testsuites'):
                    continue
                cases = list(suite.iter('testcase'))
                declared = {}
                for key in ('tests', 'failures', 'errors', 'skipped', 'flakes'):
                    value = suite.get(key)
                    if value is not None:
                        if not value.isascii() or not value.isdecimal():
                            raise ValueError('Invalid non-negative integer counter ' + key + '=' + repr(value))
                        declared[key] = int(value)
                actual = {'tests': len(cases),
                          'failures': sum(c.find('failure') is not None for c in cases),
                          'errors': sum(c.find('error') is not None for c in cases),
                          'skipped': sum(c.find('skipped') is not None for c in cases)}
                label = str(relative) + ' [' + suite.get('name', suite.tag) + ']'
                result['suite_counts'].append({'report': str(relative),
                    'suite': suite.get('name', suite.tag), 'declared': declared, 'serialized': actual})
                for key, count in actual.items():
                    if key not in declared or declared[key] == count:
                        continue
                    message = label + ': ' + key + ' declared=' + str(declared[key]) + ', serialized=' + str(count)
                    # JDT/Tycho suite headers can undercount serialized executions.
                    # Keep this discrepancy visible, but count the actual cases.
                    # A larger declared count still means potentially missing data.
                    result['errors' if declared[key] > count else 'warnings'].append(message)
                if declared.get('flakes', 0):
                    result['errors'].append(label + ': flaky executions reported')
                if any(suite.find(tag) is not None for tag in failure_tags):
                    result['errors'].append(label + ': suite failure outside a testcase')
            cases = list(root.iter('testcase'))
            result['tests'] += len(cases)
            for case in cases:
                key = case.get('classname', '') + '.' + case.get('name', '')
                failures = [node for node in case if node.tag in failure_tags]
                skipped = case.find('skipped') is not None and not failures
                result['skipped'] += int(skipped)
                if not skipped:
                    executed_modules.add(module)
                result['cases'].append({'test': key, 'report': str(relative), 'time': case.get('time'),
                                        'status': 'failed' if failures else 'skipped' if skipped else 'passed'})
                for failure in failures:
                    result['failures'].append({'test': key, 'report': str(relative), 'kind': failure.tag,
                        'message': failure.get('message', ''), 'trace': failure.text or ''})
        except (OSError, ET.ParseError, ValueError) as error:
            result['errors'].append(str(relative) + ': ' + str(error))
    required = (['org.eclipse.jdt.debug.jdi.tests', 'org.eclipse.jdt.debug.tests']
                if project == 'debug' else ['org.eclipse.jdt.core.tests.model', 'org.eclipse.jdt.core.tests.compiler'])
    result['modules'] = sorted(modules)
    result['executed_test_modules'] = sorted(executed_modules)
    result['missing_test_modules'] = sorted(set(required) - executed_modules)
    result['passed'] = sum(c['status'] == 'passed' for c in result['cases'])
    result['ok'] = (result['tests'] > result['skipped'] and not result['failures']
                    and not result['errors'] and not result['missing_test_modules'])
    return result


def validate_build(result, codes, evidence, project):
    result['build_exit_codes'] = codes
    expected = 2 if project == 'core' else 1
    if (not isinstance(codes, list) or len(codes) != expected
            or any(type(code) is not int or code != 0 for code in codes)):
        result['errors'].append('Build phases did not all complete successfully: ' + repr(codes))
    for marker in ('TIMEOUT', 'HARNESS_ERROR'):
        if (evidence / marker).exists():
            result['errors'].append('Build evidence contains ' + marker)
    result['ok'] = result['ok'] and not result['errors']


def reanalyze(evidence, project):
    """Re-read archived XML without changing raw evidence or running Maven."""
    result = analyze(evidence / 'reports', project)
    try:
        raw = (evidence / 'result.json').read_bytes()
        original = json.loads(raw)
        source = json.loads((evidence / 'source.json').read_text())
        if not isinstance(original, dict) or not isinstance(source, dict):
            raise ValueError('Evidence metadata must be JSON objects')
        if source.get('project') != project:
            raise ValueError('Archived source project does not match requested project')
        result['source'] = source
        result['original_result_sha256'] = hashlib.sha256(raw).hexdigest()
        validate_build(result, original.get('build_exit_codes'), evidence, project)
    except (OSError, ValueError) as error:
        result['errors'].append('Cannot validate archived build: ' + str(error))
        result['ok'] = False
    result['analyzer_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return result


def collect(source, evidence, project, codes):
    result = analyze(source, project)
    validate_build(result, codes, evidence, project)
    write_json(evidence / 'result.json', result)
    # Copy only diagnostic products, never the checkout's Git credentials or settings.
    patterns = ('**/target/surefire-reports/*', '**/target/work/data/.metadata/*.log',
                '**/target/compilelogs/*.xml', '**/target/apianalysis/*.xml', '**/hs_err_pid*.log')
    for pattern in patterns:
        for path in source.glob(pattern):
            if path.is_file():
                dest = evidence / 'reports' / path.relative_to(source)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
    inventory = {}
    repo = source.parent / '.m2/repository'
    for path in repo.rglob('*'):
        if path.is_file() and path.suffix in ('.jar', '.pom', '.target'):
            key = str(path.relative_to(repo))
            if '/99.99/' not in key and not key.startswith('org/eclipse/jdt/org.eclipse.jdt.core.compiler.batch/'):
                with path.open('rb') as stream:
                    inventory[key] = hashlib.file_digest(stream, 'sha256').hexdigest()
    write_json(evidence / 'external-dependency-hashes.json', inventory)
    brief = {key: value for key, value in result.items() if key not in ('cases', 'failures', 'suite_counts')}
    print(json.dumps(brief, indent=2), flush=True)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as out:
            out.write('## Result (raw failures are never suppressed)\n\n```json\n'
                      + json.dumps(brief, indent=2) + '\n```\n')
            for failure in result['failures'][:15]:
                out.write('\n- `' + failure['test'].replace('`', '') + '`: '
                          + failure['message'].replace('\n', ' ')[:300] + '\n')
    return result['ok']


def preflight(source, evidence):
    """Reject setup errors before starting an expensive build or modifying source."""
    shallow = call(['git', 'rev-parse', '--is-shallow-repository'], source).strip()
    if shallow != 'false':
        raise RuntimeError('Full Git history is required for Tycho/JGit bundle qualifiers')
    toolchains = ET.parse(Path.home() / '.m2/toolchains.xml').getroot()
    available = {node.findtext('./provides/id'): node.findtext('./configuration/jdkHome')
                 for node in toolchains.findall('toolchain')}
    required = set()
    declarations = {}
    # Only reactor bundle manifests, not intentionally broken test-workspace fixtures.
    for manifest in source.glob('*/META-INF/MANIFEST.MF'):
        text = manifest.read_text().replace('\r\n', '\n').replace('\n ', '')
        for line in text.splitlines():
            if line.startswith('Bundle-RequiredExecutionEnvironment:'):
                environments = [v.strip() for v in line.split(':', 1)[1].split(',')]
                declarations[str(manifest.relative_to(source))] = environments
                required.update(environments)
    missing = sorted(required - available.keys())
    invalid = [name for name in required & available.keys()
               if not available[name] or not Path(available[name], 'bin/java').is_file()]
    write_json(evidence / 'toolchain-preflight.json', {
        'shallow': shallow, 'manifest_environments': declarations,
        'available_toolchains': available, 'missing': missing, 'invalid': invalid})
    if missing or invalid:
        raise RuntimeError('BREE toolchain setup incomplete: ' + str(missing + invalid))


def build(args):
    source, evidence = Path(args.source).resolve(), Path(args.evidence).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    codes = []
    try:
        preflight(source, evidence)
        prepare_source(source, args.project, args.variant, evidence)
        (evidence / 'environment.txt').write_text(call(['java', '-XshowSettings:properties', '-version'])
             + call(['mvn', '-version']) + call(['uname', '-a']) + Path('/etc/os-release').read_text())
        snapshot(evidence, 'before-build')
        repo = source.parent / '.m2/repository'
        repo.mkdir(parents=True, exist_ok=True)
        tmp = source.parent / 'tmp'
        tmp.mkdir(exist_ok=True)
        os.environ.pop('JAVA_TOOL_OPTIONS', None)
        os.environ.pop('_JAVA_OPTIONS', None)
        deadline = time.monotonic() + (5400 if args.project == 'core' else 2400)
        local = '-Dmaven.repo.local=' + str(repo)
        if args.project == 'core':
            codes.append(bounded_build(['mvn', 'clean', 'install', '-f', 'org.eclipse.jdt.core.compiler.batch',
                '-DlocalEcjVersion=99.99', local, '-DcompilerBaselineMode=disable',
                '-DcompilerBaselineReplace=none'], source, evidence, 'bootstrap-ecj', deadline))
            if codes[-1]:
                return False
        command = ['mvn'] + (['-U'] if args.project == 'core' else []) + [
            'clean', 'verify', '--batch-mode', '--fail-at-end', local,
            '-Ptest-on-javase-26', '-Pbree-libs', '-Papi-check', '-Pjavadoc',
            '-Dmaven.test.failure.ignore=true', '-Dcompare-version-with-baselines.skip=false',
            '-Dproject.build.sourceEncoding=UTF-8', '-DDetectVMInstallationsJob.disabled=true',
            '-Dtycho.apitools.debug', '-DtrimStackTrace=false']
        if args.project == 'core':
            command += ['-Pp2-repo', '-Djava.io.tmpdir=' + str(tmp),
                '-Dtycho.surefire.argLine=--add-modules ALL-SYSTEM -Dcompliance=1.8,11,17,21,25,26 -Djdt.performance.asserts=disabled',
                '-Dtycho.debug.artifactcomparator', '-e', '-Dcbi-ecj-version=99.99']
        else:
            command = ['xvfb-run', '-a', '-s', '-screen 0 1280x1024x24', *command]
        codes.append(bounded_build(command, source, evidence, 'verify', deadline))
    except Exception as error:
        codes.append(125)
        (evidence / 'HARNESS_ERROR').write_text(repr(error) + '\n')
        print(repr(error), file=sys.stderr)
    finally:
        success = collect(source, evidence, args.project, codes)
    return success


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['matrix', 'build', 'reanalyze'])
    parser.add_argument('--project', choices=['core', 'debug'], required=True)
    parser.add_argument('--diagnostics', action='store_true')
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--variant', default='current')
    parser.add_argument('--source', default='source')
    parser.add_argument('--evidence', default='evidence')
    args = parser.parse_args()
    if args.mode == 'matrix':
        print(json.dumps({'include': matrix(args.project, args.diagnostics, args.ref)}))
        return 0
    if args.mode == 'reanalyze':
        evidence = Path(args.evidence).resolve()
        result = reanalyze(evidence, args.project)
        write_json(evidence / 'reanalyzed-result.json', result)
        brief = {key: value for key, value in result.items() if key not in ('cases', 'suite_counts')}
        print(json.dumps(brief, indent=2))
        return 0 if result['ok'] else 1
    return 0 if build(args) else 1


if __name__ == '__main__':
    sys.exit(main())
