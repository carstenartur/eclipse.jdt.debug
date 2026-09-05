/*******************************************************************************
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
import java.util.concurrent.ExecutionException;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import junit.framework.TestCase;

/** Tests the startup deadline with a real socket and the real JDI connector. */
public class VMConnectionTimeoutTest extends TestCase {

	public void testPeerThatDoesNotCompleteHandshakeCannotBlockStartup() throws Exception {
		int previousPort = AbstractJDITest.fBackEndPort;
		ConnectionProbe probe = new ConnectionProbe();
		FutureTask<Void> attempt = new FutureTask<>(() -> {
			probe.connectToVM();
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
				// Do not send the handshake back. The startup deadline must expire
				// without depending on the peer to close the connection.
				try {
					attempt.get(10, TimeUnit.SECONDS);
					fail("A peer without a JDWP handshake must not be accepted as a VM");
				} catch (ExecutionException expected) {
					assertTrue("Startup must report its ordinary connection failure: " + expected.getCause(), expected.getCause() instanceof Error);
					assertEquals("Could not contact the VM", expected.getCause().getMessage());
				} catch (TimeoutException expected) {
					fail("The connector blocked past the startup deadline on a silent peer");
				}
			}
		} finally {
			// Closing the peer also releases the old, unbounded implementation,
			// so the regression test does not leave a blocked startup behind.
			try {
				connecting.join(10000);
				assertFalse("Startup thread did not terminate after the peer closed", connecting.isAlive());
			} finally {
				probe.stopConsoleTestReaders();
				AbstractJDITest.fBackEndPort = previousPort;
			}
		}
	}

	private static final class ConnectionProbe extends AbstractJDITest {
		ConnectionProbe() {
			// Only the process streams are substituted: connectToVM and its
			// connector perform their real socket/handshake operations.
			fLaunchedVM = new StreamOnlyProcess();
		}

		@Override
		public void localSetUp() {
			// No target program is required for this transport-level failure.
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
		public void destroy() {
			alive = false;
		}
	}
}
