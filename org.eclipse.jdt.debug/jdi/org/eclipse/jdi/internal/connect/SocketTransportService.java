/*******************************************************************************
 * Copyright (c) 2000, 2003 IBM Corporation and others.
 * All rights reserved. This program and the accompanying materials 
 * are made available under the terms of the Common Public License v1.0
 * which accompanies this distribution, and is available at
 * http://www.eclipse.org/legal/cpl-v10.html
 * 
 * Contributors:
 *     IBM Corporation - initial API and implementation
 *******************************************************************************/
package org.eclipse.jdi.internal.connect;

import java.io.DataInputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.util.Arrays;

import com.sun.jdi.connect.TransportTimeoutException;
import com.sun.jdi.connect.spi.ClosedConnectionException;
import com.sun.jdi.connect.spi.Connection;
import com.sun.jdi.connect.spi.TransportService;

public class SocketTransportService extends TransportService {
    /** Handshake bytes used just after connecting VM. */
    private static final byte[] handshakeBytes = "JDWP-Handshake".getBytes(); //$NON-NLS-1$

    private Capabilities fCapabilities = new Capabilities() {
        public boolean supportsAcceptTimeout() {
            return false;
        }

        public boolean supportsAttachTimeout() {
            return false;
        }

        public boolean supportsHandshakeTimeout() {
            return false;
        }

        public boolean supportsMultipleConnections() {
            return false;
        }
    };

    private class SocketListenKey extends ListenKey {
        private String fAddress;

        SocketListenKey(String address) {
            fAddress = address;
        }

        /*
         * (non-Javadoc)
         * 
         * @see com.sun.jdi.connect.spi.TransportService.ListenKey#address()
         */
        public String address() {
            return fAddress;
        }
    }

    // for attaching connector
    private Socket fSocket;

    private InputStream fInput;

    private OutputStream fOutput;

    // for listening or accepting connectors
    private ServerSocket fServerSocket;

    /*
     * (non-Javadoc)
     * 
     * @see com.sun.jdi.connect.spi.TransportService#accept(com.sun.jdi.connect.spi.TransportService.ListenKey,
     *      long, long)
     */
    public Connection accept(ListenKey listenKey, long attachTimeout, long handshakeTimeout) throws IOException {
        if (attachTimeout > 0){
            if (attachTimeout > Integer.MAX_VALUE) {
                attachTimeout = Integer.MAX_VALUE;  //approx 25 days!
            }
            fServerSocket.setSoTimeout((int) attachTimeout);
        }
        try {
            fSocket = fServerSocket.accept();
        } catch (SocketTimeoutException e) {
            throw new TransportTimeoutException();
        }
        fInput = fSocket.getInputStream();
        fOutput = fSocket.getOutputStream();
        performHandshake(fInput, fOutput, handshakeTimeout);
        return new SocketConnection(this);
    }

    /*
     * (non-Javadoc)
     * 
     * @see com.sun.jdi.connect.spi.TransportService#attach(java.lang.String,
     *      long, long)
     */
    public Connection attach(String address, long attachTimeout, long handshakeTimeout) throws IOException {
        String[] strings = address.split(":"); //$NON-NLS-1$
        String host = "localhost"; //$NON-NLS-1$
        int port = 0;
        if (strings.length == 2) {
            host = strings[0];
            port = Integer.parseInt(strings[1]);
        } else {
            port = Integer.parseInt(strings[0]);
        }

        return attach(host, port, attachTimeout, handshakeTimeout);
    }

    public Connection attach(String host, int port, long attachTimeout, long handshakeTimeout) throws IOException {
        if (attachTimeout > 0){
            if (attachTimeout > Integer.MAX_VALUE) {
                attachTimeout = Integer.MAX_VALUE;  //approx 25 days!
            }
            fSocket.setSoTimeout((int) attachTimeout);
        }
        try {
            fSocket = new Socket(host, port);
        } catch (SocketTimeoutException e) {
            throw new TransportTimeoutException();
        }
        fInput = fSocket.getInputStream();
        fOutput = fSocket.getOutputStream();
        performHandshake(fInput, fOutput, handshakeTimeout);
        return new SocketConnection(this);
    }

    void performHandshake(final InputStream in, final OutputStream out, final long timeout) throws IOException {
        final Object lock = new Object();
        final IOException[] ex = new IOException[1];
        final boolean[] handshakeCompleted = new boolean[1];
        
        Thread t = new Thread(new Runnable() {
            public void run() {
                try {
                    writeHandshake(out);
                    readHandshake(in);
                    synchronized(lock) {
                        handshakeCompleted[0] = true;
                        lock.notify();
                    }
                } catch (IOException e) {
                    ex[0] = e;
                }
            }
        });
        
        t.start();
        synchronized(lock) {
            try {
	            if (!handshakeCompleted[0]) 
	                lock.wait(timeout);
            } catch (InterruptedException e) {
            }
        }
        
        if (handshakeCompleted[0])
            return;
        
        if (ex[0] != null)
            throw ex[0];
        
        try {
	        in.close();
	        out.close();
        } catch (IOException e) {
        }
        
        throw new TransportTimeoutException();
    }
    
    private void readHandshake(InputStream input) throws IOException {
        try {
            DataInputStream in = new DataInputStream(input);
            byte[] handshakeInput = new byte[handshakeBytes.length];
            in.readFully(handshakeInput);
            if (!Arrays.equals(handshakeInput, handshakeBytes))
                throw new IOException("Received invalid handshake"); //$NON-NLS-1$
        } catch (EOFException e) {
            throw new ClosedConnectionException();
        }
    }

    private void writeHandshake(OutputStream out) throws IOException {
        out.write(handshakeBytes);
    }

    /*
     * (non-Javadoc)
     * 
     * @see com.sun.jdi.connect.spi.TransportService#capabilities()
     */
    public Capabilities capabilities() {
        return fCapabilities;
    }

    /*
     * (non-Javadoc)
     * 
     * @see com.sun.jdi.connect.spi.TransportService#description()
     */
    public String description() {
        return "org.eclipse.jdt.debug: Socket Implementation of TransportService"; //$NON-NLS-1$
    }

    /*
     * (non-Javadoc)
     * 
     * @see com.sun.jdi.connect.spi.TransportService#name()
     */
    public String name() {
        return "org.eclipse.jdt.debug_SocketTransportService"; //$NON-NLS-1$
    }

    /*
     * (non-Javadoc)
     * 
     * @see com.sun.jdi.connect.spi.TransportService#startListening()
     */
    public ListenKey startListening() throws IOException {
        // not used by jdt debug.
        return startListening(null);
    }

    /*
     * (non-Javadoc)
     * 
     * @see com.sun.jdi.connect.spi.TransportService#startListening(java.lang.String)
     */
    public ListenKey startListening(String address) throws IOException {
        String host = null;
        int port = 8888; // jdt debugger will always specify an address in
                            // the form localhost:port
        if (address != null) {
            String[] strings = address.split(":"); //$NON-NLS-1$
            host = "localhost"; //$NON-NLS-1$
            if (strings.length == 2) {
                host = strings[0];
                port = Integer.parseInt(strings[1]);
            } else {
                port = Integer.parseInt(strings[0]);
            }
        }
        if (host == null) {
            host = "localhost"; //$NON-NLS-1$
        }

        fServerSocket = new ServerSocket(port);
        ListenKey listenKey = new SocketListenKey(host + ":" + port); //$NON-NLS-1$
        return listenKey;
    }

    /*
     * (non-Javadoc)
     * 
     * @see com.sun.jdi.connect.spi.TransportService#stopListening(com.sun.jdi.connect.spi.TransportService.ListenKey)
     */
    public void stopListening(ListenKey arg1) throws IOException {
        if (fServerSocket != null) {
            try {
                fServerSocket.close();
            } catch (IOException e) {
            }
        }
        fServerSocket = null;
    }

    public void close() {
        if (fSocket != null) {
            try {
                fSocket.close();
            } catch (IOException e) {
            }
        }
 
        fServerSocket = null;
        fSocket = null;
        fInput = null;
        fOutput = null;
    }

    /**
     * @return
     */
    public InputStream getInputStream() {
        return fInput;
    }

    /**
     * @return
     */
    public OutputStream getOutputStream() {
        return fOutput;
    }
}
