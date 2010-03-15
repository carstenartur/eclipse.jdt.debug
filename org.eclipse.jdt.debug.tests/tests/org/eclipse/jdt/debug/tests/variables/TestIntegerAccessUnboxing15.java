/*******************************************************************************
 * Copyright (c) 2010 IBM Corporation and others.
 * All rights reserved. This program and the accompanying materials
 * are made available under the terms of the Eclipse Public License v1.0
 * which accompanies this distribution, and is available at
 * http://www.eclipse.org/legal/epl-v10.html
 *
 * Contributors:
 *     IBM Corporation - initial API and implementation
 *******************************************************************************/
package org.eclipse.jdt.debug.tests.variables;

import org.eclipse.debug.core.DebugEvent;
import org.eclipse.debug.core.model.IBreakpoint;
import org.eclipse.jdt.debug.core.IJavaDebugTarget;
import org.eclipse.jdt.debug.core.IJavaStackFrame;
import org.eclipse.jdt.debug.core.IJavaThread;
import org.eclipse.jdt.debug.eval.EvaluationManager;
import org.eclipse.jdt.debug.eval.IAstEvaluationEngine;
import org.eclipse.jdt.debug.eval.IEvaluationListener;
import org.eclipse.jdt.debug.eval.IEvaluationResult;
import org.eclipse.jdt.debug.tests.AbstractDebugTest;

/**
 * Tests that arrays can be accessed with *big* Integers
 */
public class TestIntegerAccessUnboxing15 extends AbstractDebugTest {

	public TestIntegerAccessUnboxing15(String name) {
		super(name);
	}
	
	class Listener implements IEvaluationListener {
		
		private Object lock = new Object();
		private IEvaluationResult result;

		/* (non-Javadoc)
		 * @see org.eclipse.jdt.debug.eval.IEvaluationListener#evaluationComplete(org.eclipse.jdt.debug.eval.IEvaluationResult)
		 */
		public void evaluationComplete(IEvaluationResult result) {
			synchronized (lock) {
				this.result = result;
				lock.notifyAll();
			}
		}
		
		IEvaluationResult getResult() throws Exception {
			synchronized (lock) {
				if (result == null) {
					lock.wait(DEFAULT_TIMEOUT);
				}
			}
			assertNotNull("Evaluation did not complete", result);
			return result;
		}
		
	}
	
	public void doAccessTest(String snippet, int expected) throws Exception {
		IJavaThread thread= null;
		IAstEvaluationEngine engine = null;
		String typeName = "a.b.c.IntegerAccess";
		createLineBreakpoint(get15Project().findType(typeName), 24);
		try {
			thread= launchToBreakpoint(get15Project(), typeName);
			assertNotNull("Breakpoint not hit within timeout period", thread);
			
			IBreakpoint hit = getBreakpoint(thread);
			assertNotNull("suspended, but not by breakpoint", hit);
			IJavaDebugTarget target = (IJavaDebugTarget) thread.getDebugTarget();
			
			IJavaStackFrame frame = (IJavaStackFrame) thread.getTopStackFrame();
			engine = EvaluationManager.newAstEvaluationEngine(get15Project(), target);
			Listener listener = new Listener();
			engine.evaluate(snippet, frame, listener, DebugEvent.EVALUATION, false);
			IEvaluationResult result = listener.getResult();
			assertFalse("Should be no errors in evaluation", result.hasErrors());
			assertEquals(target.newValue(expected), result.getValue());
		} finally {
			if (engine != null) {
				engine.dispose();
			}
			terminateAndRemove(thread);
			removeAllBreakpoints();
		}
	}	
	
	/**
	 * Test a row can be accessed
	 * 
	 * @throws Exception
	 */
	public void testRowAccess() throws Exception {
		doAccessTest("matrix[new Integer(0)][0]", 1);
	}
	
	/**
	 * Test a column can be accessed.
	 * 
	 * @throws Exception
	 */
	public void testColumnAccess() throws Exception {
		doAccessTest("matrix[2][new Integer(2)]", 9);
	}

	public void testRowColumnAccess() throws Exception {
		doAccessTest("matrix[1][new Integer(1)]", 5);
	}
}
