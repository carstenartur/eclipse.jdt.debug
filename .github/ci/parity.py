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
              'errors': [], 'modules': [], 'cases': []}
    modules = set()
    for report in reports:
        relative = report.relative_to(source)
        modules.add(relative.parts[0])
        try:
            root = ET.parse(report).getroot()
            if root.tag not in ('testsuite', 'testsuites'):
                raise ValueError('Not a JUnit test report')
            cases = list(root.iter('testcase'))
            if root.get('tests') is not None and int(root.get('tests')) != len(cases):
                result['errors'].append(str(relative) + ': declared test count differs from serialized cases')
            declared_failed = int(root.get('failures', '0')) + int(root.get('errors', '0'))
            actual_failed = sum(len(c.findall('failure')) + len(c.findall('error')) for c in cases)
            if declared_failed > actual_failed:
                result['errors'].append(str(relative) + ': failure counters lack matching failure details')
            result['tests'] += len(cases)
            for case in cases:
                key = case.get('classname', '') + '.' + case.get('name', '')
                skipped = case.find('skipped') is not None
                result['skipped'] += int(skipped)
                failures = list(case.findall('failure')) + list(case.findall('error'))
                result['cases'].append({'test': key, 'time': case.get('time'),
                                        'status': 'failed' if failures else 'skipped' if skipped else 'passed'})
                for failure in failures:
                    result['failures'].append({'test': key, 'report': str(relative),
                        'message': failure.get('message', ''), 'trace': failure.text or ''})
            if not cases and (int(root.get('failures', '0')) or int(root.get('errors', '0'))):
                result['errors'].append(str(relative) + ': suite error without test cases')
        except (OSError, ET.ParseError, ValueError) as error:
            result['errors'].append(str(relative) + ': ' + str(error))
    required = (['org.eclipse.jdt.debug.jdi.tests', 'org.eclipse.jdt.debug.tests']
                if project == 'debug' else ['org.eclipse.jdt.core.tests.model', 'org.eclipse.jdt.core.tests.compiler'])
    result['modules'] = sorted(modules)
    result['missing_test_modules'] = sorted(set(required) - modules)
    result['passed'] = result['tests'] - result['skipped'] - sum(c['status'] == 'failed' for c in result['cases'])
    result['ok'] = (result['tests'] > result['skipped'] and not result['failures']
                    and not result['errors'] and not result['missing_test_modules'])
    return result


def collect(source, evidence, project, codes):
    result = analyze(source, project)
    result['build_exit_codes'] = codes
    result['ok'] = result['ok'] and bool(codes) and all(code == 0 for code in codes)
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
    brief = {key: value for key, value in result.items() if key not in ('cases', 'failures')}
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
    parser.add_argument('mode', choices=['matrix', 'build'])
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
    return 0 if build(args) else 1


if __name__ == '__main__':
    sys.exit(main())
