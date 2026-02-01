
	protected void deregisterRequest(EventRequest request, JDIDebugTarget target)
			throws CoreException {
		target.removeJDIEventListener(this, request);
		// A request may be getting de-registered because the breakpoint has
		// been deleted. It may be that this occurred because of a marker
		// deletion.
		// Don't try updating the marker (decrementing the install count) if
		// it no longer exists.
		IMarker marker = getMarker();
		if (!(request instanceof ClassPrepareRequest) && marker != null && marker.exists()) {
			decrementInstallCount();
		}
	}