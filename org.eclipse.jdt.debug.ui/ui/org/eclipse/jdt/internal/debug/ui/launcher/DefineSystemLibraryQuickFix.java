package org.eclipse.jdt.internal.debug.ui.launcher;

/**********************************************************************
Copyright (c) 2002 IBM Corp. and others. All rights reserved.
This file is made available under the terms of the Common Public License v1.0
which accompanies this distribution, and is available at
http://www.eclipse.org/legal/cpl-v10.html
**********************************************************************/

import org.eclipse.core.resources.IMarker;
import org.eclipse.jdt.internal.debug.ui.JDIDebugUIPlugin;
import org.eclipse.jface.preference.IPreferenceNode;
import org.eclipse.jface.preference.IPreferencePage;
import org.eclipse.jface.preference.PreferenceDialog;
import org.eclipse.jface.preference.PreferenceManager;
import org.eclipse.jface.preference.PreferenceNode;
import org.eclipse.swt.custom.BusyIndicator;
import org.eclipse.ui.IMarkerResolution;

/**
 * Quick fix to define a new system library (none were found). 
 */
public class DefineSystemLibraryQuickFix implements IMarkerResolution {
	
	public DefineSystemLibraryQuickFix() {
		super();
	}

	/**
	 * @see org.eclipse.ui.IMarkerResolution#run(org.eclipse.core.resources.IMarker)
	 */
	public void run(IMarker marker) {
		IPreferencePage page = new VMPreferencePage();
		showPreferencePage("org.eclipse.jdt.debug.ui.preferences.VMPreferencePage", page);	 //$NON-NLS-1$
	}
	
	/**
	 * @see org.eclipse.ui.IMarkerResolution#getLabel()
	 */
	public String getLabel() {
		return LauncherMessages.getString("DefineSystemLibraryQuickFix.Create_a_system_library_definition_2"); //$NON-NLS-1$
	}

	protected void showPreferencePage(String id, IPreferencePage page) {
		final IPreferenceNode targetNode = new PreferenceNode(id, page);
		
		PreferenceManager manager = new PreferenceManager();
		manager.addToRoot(targetNode);
		final PreferenceDialog dialog = new PreferenceDialog(JDIDebugUIPlugin.getActiveWorkbenchShell(), manager);
		final boolean [] result = new boolean[] { false };
		BusyIndicator.showWhile(JDIDebugUIPlugin.getStandardDisplay(), new Runnable() {
			public void run() {
				dialog.create();
				dialog.setMessage(targetNode.getLabelText());
				result[0]= (dialog.open() == PreferenceDialog.OK);
			}
		});		
	}
}
