package org.eclipse.jdt.debug.tests.console;

import java.io.IOException;
import java.io.PrintStream;

import org.eclipse.debug.ui.DebugUITools;
import org.eclipse.debug.ui.IDebugUIConstants;
import org.eclipse.jface.action.IAction;
import org.eclipse.jface.viewers.ISelection;
import org.eclipse.swt.SWT;
import org.eclipse.swt.widgets.Display;
import org.eclipse.swt.widgets.Event;
import org.eclipse.ui.IActionDelegate2;
import org.eclipse.ui.IWorkbenchWindow;
import org.eclipse.ui.IWorkbenchWindowActionDelegate;
import org.eclipse.ui.console.ConsolePlugin;
import org.eclipse.ui.console.IConsole;
import org.eclipse.ui.console.IConsoleManager;
import org.eclipse.ui.console.IOConsole;
import org.eclipse.ui.console.IOConsoleInputStream;
import org.eclipse.ui.console.IOConsoleOutputStream;

public class IOConsoleEchoActionDelegate implements IActionDelegate2, IWorkbenchWindowActionDelegate {

    public void init(IAction action) {
    }

    public void dispose() {
    }

    public void runWithEvent(IAction action, Event event) {
        run(action);
    }

    public void run(IAction action) {
        new Thread(new Runnable() {
            public void run() {
                runTest();
            }
        }, "IOConsole Test Thread").start(); //$NON-NLS-1$
    }
    
    public void runTest() {
        final IOConsole console = new IOConsole("IO Test Console", DebugUITools.getImageDescriptor(IDebugUIConstants.IMG_ACT_RUN)); //$NON-NLS-1$
        console.setWordWrap(true);
        
        final Display display = Display.getDefault();
        
        final IOConsoleInputStream in = console.getInputStream();
        display.asyncExec(new Runnable() {
            public void run() {        
                in.setColor(display.getSystemColor(SWT.COLOR_BLUE));
            }
        });
        IConsoleManager manager = ConsolePlugin.getDefault().getConsoleManager();
        manager.addConsoles(new IConsole[] { console });
        
        final IOConsoleOutputStream out = console.createOutputStream("MY STREAM YAY"); //$NON-NLS-1$
        Display.getDefault().asyncExec(new Runnable() {
            public void run() {
                out.setColor(Display.getDefault().getSystemColor(SWT.COLOR_GREEN));     
                out.setFontStyle(SWT.ITALIC);
            }
        });
        
        PrintStream ps = new PrintStream(out);
        ps.println("Any text entered should be echoed back"); //$NON-NLS-1$
        for(;;) {
            byte[] b = new byte[1024];
            int bRead = 0;
            try {
                bRead = in.read(b);
            } catch (IOException io) {
                io.printStackTrace();
            }
            
            try {
                out.write(b, 0, bRead);
                ps.println();
            } catch (IOException e) {
                e.printStackTrace();
            }
        }
    }

    public void selectionChanged(IAction action, ISelection selection) {
    }

    public void init(IWorkbenchWindow window) {
    }

}