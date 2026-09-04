from pathlib import Path
import runpy

runpy.run_path("verification/apply_test.py", run_name="__main__")


def replace_once(path: str, old: str, new: str, label: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label}, found {count}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "org.eclipse.jdt.debug/model/org/eclipse/jdt/internal/debug/core/breakpoints/JavaBreakpoint.java",
    "if (!(request instanceof ClassPrepareRequest) && getMarker().exists()) {",
    "if (!(request instanceof ClassPrepareRequest) && markerExists()) {",
    "JavaBreakpoint marker guard",
)
replace_once(
    "org.eclipse.jdt.debug/model/org/eclipse/jdt/internal/debug/core/breakpoints/JavaClassPrepareBreakpoint.java",
    "if (getMarker().exists()) {",
    "if (markerExists()) {",
    "JavaClassPrepareBreakpoint marker guard",
)

old_target = """\t@Override
\tpublic void breakpointRemoved(IBreakpoint breakpoint, IMarkerDelta delta) {
\t\tif (!isAvailable()) {
\t\t\treturn;
\t\t}
\t\tif (supportsBreakpoint(breakpoint)) {
\t\t\ttry {
\t\t\t\t((JavaBreakpoint) breakpoint).removeFromTarget(this);
\t\t\t\tgetBreakpoints().remove(breakpoint);
\t\t\t\tIterator<JDIThread> threads = getThreadIterator();
\t\t\t\twhile (threads.hasNext()) {
\t\t\t\t\tthreads.next()
\t\t\t\t\t\t\t.removeCurrentBreakpoint(breakpoint);
\t\t\t\t}
\t\t\t} catch (CoreException e) {
\t\t\t\tlogError(e);
\t\t\t}
\t\t}
\t}
"""
new_target = """\t@Override
\tpublic void breakpointRemoved(IBreakpoint breakpoint, IMarkerDelta delta) {
\t\tif (!isAvailable()) {
\t\t\treturn;
\t\t}
\t\t// A removal notification can arrive after the marker is no longer
\t\t// available. Use the target's installed state instead of marker data.
\t\tboolean installed = false;
\t\tsynchronized (fBreakpoints) {
\t\t\tfor (IBreakpoint installedBreakpoint : fBreakpoints) {
\t\t\t\tif (installedBreakpoint == breakpoint) {
\t\t\t\t\tinstalled = true;
\t\t\t\t\tbreak;
\t\t\t\t}
\t\t\t}
\t\t}
\t\tif (installed) {
\t\t\ttry {
\t\t\t\t((JavaBreakpoint) breakpoint).removeFromTarget(this);
\t\t\t} catch (CoreException e) {
\t\t\t\tlogError(e);
\t\t\t} finally {
\t\t\t\tsynchronized (fBreakpoints) {
\t\t\t\t\tfBreakpoints.removeIf(installedBreakpoint -> installedBreakpoint == breakpoint);
\t\t\t\t}
\t\t\t\tIterator<JDIThread> threads = getThreadIterator();
\t\t\t\twhile (threads.hasNext()) {
\t\t\t\t\tthreads.next().removeCurrentBreakpoint(breakpoint);
\t\t\t\t}
\t\t\t}
\t\t}
\t}
"""
replace_once(
    "org.eclipse.jdt.debug/model/org/eclipse/jdt/internal/debug/core/model/JDIDebugTarget.java",
    old_target,
    new_target,
    "JDIDebugTarget removal method",
)
replace_once(
    "org.eclipse.jdt.debug/model/org/eclipse/jdt/internal/debug/core/model/JDIThread.java",
    "\t\t\tfCurrentBreakpoints.remove(bp);",
    "\t\t\tfCurrentBreakpoints.removeIf(breakpoint -> breakpoint == bp);",
    "JDIThread identity removal",
)
replace_once(
    "org.eclipse.jdt.debug/META-INF/MANIFEST.MF",
    "Bundle-Version: 3.26.100.qualifier",
    "Bundle-Version: 3.26.200.qualifier",
    "bundle version",
)
