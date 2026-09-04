from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


path = Path("org.eclipse.jdt.debug.tests/tests/org/eclipse/jdt/debug/tests/breakpoints/JavaBreakpointListenerTests.java")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    " *  Copyright (c) 2000, 2015 IBM Corporation and others.",
    " *  Copyright (c) 2000, 2026 IBM Corporation and others.",
    "test copyright",
)
text = replace_once(
    text,
    "import org.eclipse.core.resources.IWorkspaceRunnable;",
    "import org.eclipse.core.resources.IMarker;\nimport org.eclipse.core.resources.IWorkspaceRunnable;",
    "IMarker import",
)
text = replace_once(
    text,
    "import org.eclipse.debug.core.DebugException;",
    "import org.eclipse.debug.core.DebugException;\nimport org.eclipse.debug.core.model.IBreakpoint;",
    "IBreakpoint import",
)
text = replace_once(
    text,
    "import org.eclipse.jdt.debug.tests.AbstractDebugTest;",
    "import org.eclipse.jdt.debug.tests.AbstractDebugTest;\nimport org.eclipse.jdt.internal.debug.core.model.JDIDebugTarget;",
    "JDIDebugTarget import",
)

insertion_point = "\n\t/**\n\t * Tests a breakpoint listener extension gets removal notification when the underlying\n\t * marker is deleted.\n\t */\n\tpublic void testRemovedNotification() throws Exception {"
addition = """

\tprivate static boolean containsByIdentity(IBreakpoint[] breakpoints, IBreakpoint expected) {
\t\tfor (IBreakpoint breakpoint : breakpoints) {
\t\t\tif (breakpoint == expected) {
\t\t\t\treturn true;
\t\t\t}
\t\t}
\t\treturn false;
\t}

\tprivate static boolean containsByIdentity(List<IBreakpoint> breakpoints, IBreakpoint expected) {
\t\tsynchronized (breakpoints) {
\t\t\tfor (IBreakpoint breakpoint : breakpoints) {
\t\t\t\tif (breakpoint == expected) {
\t\t\t\t\treturn true;
\t\t\t\t}
\t\t\t}
\t\t}
\t\treturn false;
\t}

\t/**
\t * Tests that a breakpoint without an associated marker is completely removed
\t * from a debug target and its suspended thread.
\t */
\tpublic void testRemovalWithoutMarker() throws Exception {
\t\tString typeName = \"HitCountLooper\";
\t\tIJavaLineBreakpoint bp = createLineBreakpoint(17, typeName);
\t\tIJavaThread thread = null;
\t\tIMarker marker = null;
\t\ttry {
\t\t\tthread = launchToLineBreakpoint(typeName, bp);
\t\t\tJDIDebugTarget target = (JDIDebugTarget) thread.getDebugTarget();
\t\t\tassertTrue(\"Breakpoint should be installed in the debug target\",
\t\t\t\t\tcontainsByIdentity(target.getBreakpoints(), bp));
\t\t\tassertTrue(\"Breakpoint should be current in the suspended thread\",
\t\t\t\t\tcontainsByIdentity(thread.getBreakpoints(), bp));

\t\t\tmarker = bp.getMarker();
\t\t\ttry {
\t\t\t\tbp.setMarker(null);
\t\t\t} catch (CoreException e) {
\t\t\t\t// Expected: reconfiguration cannot complete without a marker.
\t\t\t}
\t\t\tassertNull(\"Breakpoint should no longer have an associated marker\", bp.getMarker());

\t\t\ttarget.breakpointRemoved(bp, null);

\t\t\tassertFalse(\"Stale breakpoint remained in the debug target\",
\t\t\t\t\tcontainsByIdentity(target.getBreakpoints(), bp));
\t\t\tassertFalse(\"Stale breakpoint remained in the suspended thread\",
\t\t\t\t\tcontainsByIdentity(thread.getBreakpoints(), bp));
\t\t} finally {
\t\t\tif (bp.getMarker() == null && marker != null) {
\t\t\t\tbp.setMarker(marker);
\t\t\t}
\t\t\tterminateAndRemove(thread);
\t\t\tremoveAllBreakpoints();
\t\t}
\t}
"""
text = replace_once(text, insertion_point, addition + insertion_point, "test insertion point")
path.write_text(text, encoding="utf-8")
