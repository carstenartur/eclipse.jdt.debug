/*******************************************************************************
 * Copyright (c) 2012 Jesper Steen Moller and others.
 * All rights reserved. This program and the accompanying materials
 * are made available under the terms of the Eclipse Public License v1.0
 * which accompanies this distribution, and is available at
 * http://www.eclipse.org/legal/epl-v10.html
 * 
 * Contributors:
 *     Jesper Steen Moller - initial API and implementation, adapted from
 *     Stefan Mandels contribution in bug 341232, and existing debug tests
 *     IBM Corporation - addition test for bug 341232
 *******************************************************************************/
package org.eclipse.jdt.debug.tests.breakpoints;

import org.eclipse.jdt.core.IJavaProject;
import org.eclipse.jdt.debug.core.IJavaLineBreakpoint;
import org.eclipse.jdt.debug.core.IJavaThread;
import org.eclipse.jdt.debug.tests.AbstractDebugTest;

/**
 * Tests conditional breakpoints.
 */
public class ConditionalBreakpointsWithGenerics extends AbstractDebugTest {
	
	/**
	 * Constructor
	 * @param name
	 */
	public ConditionalBreakpointsWithGenerics(String name) {
		super(name);
	}

	/* (non-Javadoc)
	 * @see org.eclipse.jdt.debug.tests.AbstractDebugTest#getProjectContext()
	 */
	@Override
	protected IJavaProject getProjectContext() {
		return get15Project();
	}

	/**
	 * Tests a breakpoint with a simple condition does not cause errors
	 * multiple use of the same generic type 'T'
	 * 
	 * @see https://bugs.eclipse.org/bugs/show_bug.cgi?id=341232
	 * @throws Exception
	 */
	public void testDuplicateGenericTypes() throws Exception {
		String typeName = "a.b.c.ConditionalsNearGenerics";
		String innerTypeName = "a.b.c.ConditionalsNearGenerics.ItemIterator";
		IJavaLineBreakpoint bp1 = createConditionalLineBreakpoint(33, typeName, "false", true);
		IJavaLineBreakpoint bp2 = createConditionalLineBreakpoint(39, typeName, "false", true);
		IJavaLineBreakpoint bp3 = createConditionalLineBreakpoint(52, innerTypeName, "false", true);
		IJavaLineBreakpoint bp4 = createConditionalLineBreakpoint(53, innerTypeName, "true", true);
		
		IJavaThread thread= null;
		try {
			thread= launchToLineBreakpoint(typeName, bp4); // If compiled correctly, this will jump over bp1-bp3 !!

			bp1.delete();
			bp2.delete();
			bp3.delete();
			bp4.delete();
		} finally {
			terminateAndRemove(thread);
			removeAllBreakpoints();
		}		
	}
	
	/**
	 * Tests a breakpoint with a simple condition does not cause errors
	 * with many inner types with generics
	 * 
	 * @see https://bugs.eclipse.org/bugs/show_bug.cgi?id=341232
	 * @throws Exception
	 */
	public void testNestedTypes1() throws Exception {
		String type = "a.b.c.StepIntoSelectionWithGenerics";
		IJavaThread thread = null;
		try {
			createConditionalLineBreakpoint(32, type, "true", true);
			thread = launchToBreakpoint(type);
			assertNotNull("Breakpoint not hit within timeout period", thread);
		}
		finally {
			terminateAndRemove(thread);
			removeAllBreakpoints();
		}
	}
	
	/**
	 * Tests a breakpoint with a simple condition does not cause errors
	 * with many inner types with generics
	 * 
	 * @see https://bugs.eclipse.org/bugs/show_bug.cgi?id=341232
	 * @throws Exception
	 */
	public void testNestedTypes2() throws Exception {
		String type = "a.b.c.StepIntoSelectionWithGenerics";
		IJavaThread thread = null;
		try {
			createConditionalLineBreakpoint(21, type, "true", true);
			thread = launchToBreakpoint(type);
			assertNotNull("Breakpoint not hit within timeout period", thread);
		}
		finally {
			terminateAndRemove(thread);
			removeAllBreakpoints();
		}
	}
	
	/**
	 * Tests a breakpoint with a simple condition does not cause errors
	 * with many inner types with generics
	 * 
	 * @see https://bugs.eclipse.org/bugs/show_bug.cgi?id=341232
	 * @throws Exception
	 */
	public void testNestedTypes3() throws Exception {
		String type = "a.b.c.StepIntoSelectionWithGenerics";
		IJavaThread thread = null;
		try {
			createConditionalLineBreakpoint(17, type, "true", true);
			thread = launchToBreakpoint(type);
			assertNotNull("Breakpoint not hit within timeout period", thread);
		}
		finally {
			terminateAndRemove(thread);
			removeAllBreakpoints();
		}
	}
	
	/**
	 * Tests a breakpoint with a simple condition does not cause errors
	 * with multiple generic types 'T', 'E', 'K'
	 * 
	 * @see https://bugs.eclipse.org/bugs/show_bug.cgi?id=341232
	 * @throws Exception
	 */
	public void testMultipleGenericTypes1() throws Exception {
		String type = "a.b.c.MethodBreakpoints";
		IJavaThread thread = null;
		try {
			createConditionalLineBreakpoint(26, type, "true", true);
			thread = launchToBreakpoint(type);
			assertNotNull("Breakpoint not hit within timeout period", thread);
		}
		finally {
			terminateAndRemove(thread);
			removeAllBreakpoints();
		}
	}
	
	/**
	 * Tests a breakpoint with a simple condition does not cause errors
	 * with multiple generic types 'T', 'E', 'K'
	 * 
	 * @see https://bugs.eclipse.org/bugs/show_bug.cgi?id=341232
	 * @throws Exception
	 */
	public void testMultipleGenericTypes2() throws Exception {
		String type = "a.b.c.MethodBreakpoints";
		IJavaThread thread = null;
		try {
			createConditionalLineBreakpoint(31, type, "true", true);
			thread = launchToBreakpoint(type);
			assertNotNull("Breakpoint not hit within timeout period", thread);
		}
		finally {
			terminateAndRemove(thread);
			removeAllBreakpoints();
		}
	}
	
	/**
	 * Tests a breakpoint with a condition that includes generics
	 * 
	 * @see https://bugs.eclipse.org/bugs/show_bug.cgi?id=341232
	 * @throws Exception
	 */
	public void testBreakpointWithGenericsCondition1() throws Exception {
		String type = "a.b.c.MethodBreakpoints";
		IJavaThread thread = null;
		try {
			String condition = "MethodBreakpoints<Integer> breakpoints = new MethodBreakpoints<Integer>();\n"
						+ "breakpoints.typeParameter(10);\n"
						+ "return true;";
			createConditionalLineBreakpoint(31, type, condition, true);
			thread = launchToBreakpoint(type);
			assertNotNull("Breakpoint not hit within timeout period", thread);
		}
		finally {
			terminateAndRemove(thread);
			removeAllBreakpoints();
		}
	}
	
	/**
	 * Tests a breakpoint with a generified condition in a type that includes
	 * duplicate generic declarations
	 * 
	 * @see https://bugs.eclipse.org/bugs/show_bug.cgi?id=341232
	 * @throws Exception
	 */
	public void testBreakpointWithGenericCondition2() throws Exception {
		String type = "a.b.c.ConditionalsNearGenerics";
		IJavaThread thread = null;
		try {
			String condition = "Iterator<Integer> i = tokenize(Arrays.asList(1, 2, 3), \"condition\");\n"+
								"return i.hasNext();";
			createConditionalLineBreakpoint(34, type, condition, true);
			thread = launchToBreakpoint(type);
			assertNotNull("Breakpoint not hit within timeout period", thread);
		}
		finally {
			terminateAndRemove(thread);
			removeAllBreakpoints();
		}
	}
	
	/**
	 * Tests a breakpoint with a condition that includes generics from nested classes
	 * 
	 * @see https://bugs.eclipse.org/bugs/show_bug.cgi?id=341232
	 * @throws Exception
	 */
	public void testBreakpointWithGenericCondition3() throws Exception {
		String type = "a.b.c.StepIntoSelectionWithGenerics";
		IJavaThread thread = null;
		try {
			String condition = "StepIntoSelectionWithGenerics<String> ssswg = new StepIntoSelectionWithGenerics<String>();\n"
					+ "InnerCLazz<Integer> ic = new InnerClazz<Integer>();\n"
					+ "InnerClazz2<Double> ic2 = new InnerClazz2<Double>();\n"
					+ "ic2.hello();\n"
					+ "return true;";
			createConditionalLineBreakpoint(32, type, condition, true);
			thread = launchToBreakpoint(type);
			assertNotNull("Breakpoint not hit within timeout period", thread);
		}
		finally {
			terminateAndRemove(thread);
			removeAllBreakpoints();
		}
	}
}