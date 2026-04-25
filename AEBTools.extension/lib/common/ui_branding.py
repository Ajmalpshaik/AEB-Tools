# -*- coding: utf-8 -*-
"""
Tool Name    : UI Branding Helpers
Purpose      : Centralize shared branding text for custom pyRevit windows and Revit task dialogs
Author       : Ajmal P.S.
Company      : AEB Tools
Version      : 1.0.0
Created      : 2026-04-21
Last Updated : 2026-04-21
Target       : Revit 2020-2027
Platform     : pyRevit / Python
Dependencies : Python standard library
Input        : WPF window instances or Revit task dialog instances
Output       : Applied branding footer text for supported UI surfaces
Notes        : Use this helper whenever a custom window or dialog is created in the extension
Changelog    : v1.0.0 - Added centralized AEB Tools UI branding footer helpers
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from __future__ import absolute_import, division, print_function


WINDOW_FOOTER_TEXT = u"All Rights Reserved \u00A9 Ajmal P.S. | AEB Tools"


def apply_window_footer(window, footer_control_name="brandingFooterTextBlock"):
    footer_control = getattr(window, footer_control_name, None)
    if footer_control is None:
        return False

    footer_control.Text = WINDOW_FOOTER_TEXT
    return True


def apply_task_dialog_footer(dialog):
    try:
        dialog.FooterText = WINDOW_FOOTER_TEXT
        return True
    except Exception:
        return False
