# -*- coding: utf-8 -*-
"""
Tool Name    : Auto Dimension
Purpose      : Automatically create clean plan dimensions for rooms, grids, and overall building size.
Author       : Ajmal P.S.
Company      : AJ Tools
Version      : 1.0.0
Created      : 2026-04-25
Last Updated : 2026-04-26
Target       : Revit 2020-2027
Platform     : pyRevit / IronPython
Dependencies : Autodesk Revit API, pyRevit
Input        : Active plan view, rooms, grids, walls, selected dimension options, offset distance, and dimension type.
Output       : Clean internal room, external grid, and overall building dimensions.
Notes        : Uses view-aware and scale-safe dimension placement for stable BIM drafting output.
Changelog    : v1.0.1 - Stabilised internal room dimensions across split boundary segments.
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from __future__ import absolute_import, division, print_function

import os
import sys

_BUNDLE_DIR = os.path.dirname(__file__)
if _BUNDLE_DIR not in sys.path:
    sys.path.insert(0, _BUNDLE_DIR)

from Autodesk.Revit.DB import View, ViewType
from Autodesk.Revit.UI import TaskDialog, TaskDialogCommonButtons

try:
    from pyrevit import script as pyrevit_script
except Exception:
    pyrevit_script = None

import constants
import service
import ui
import utils

__title__ = "Auto Dimension"
__author__ = "Ajmal P.S."
__doc__ = "Create clean plan dimensions for rooms, grids, and overall building size."


_PLAN_VIEW_TYPES = (
    ViewType.FloorPlan,
    ViewType.CeilingPlan,
    ViewType.AreaPlan,
    ViewType.EngineeringPlan,
)


def main():
    _uidoc, doc, view = _validate_runtime()
    if doc is None:
        return

    request = ui.show_options_dialog(doc)
    if request is None:
        return

    view_frame = utils.build_view_frame(view)
    if view_frame is None:
        _show_message(
            constants.WINDOW_TITLE,
            "The active view does not expose a usable coordinate frame.",
        )
        return

    report = service.run(doc, view, view_frame, request)
    _print_output_report(report)
    _show_message(constants.REPORT_TITLE, _report_instruction(report), _format_report(report))


def _validate_runtime():
    uidoc = getattr(__revit__, "ActiveUIDocument", None)
    if uidoc is None:
        _show_message(
            constants.WINDOW_TITLE,
            "Open a Revit project document before running this tool.",
        )
        return None, None, None

    doc = uidoc.Document
    if doc is None or getattr(doc, "IsFamilyDocument", False):
        _show_message(
            constants.WINDOW_TITLE,
            "Open a Revit project document before running this tool.",
        )
        return None, None, None

    view = getattr(doc, "ActiveView", None)
    if not _is_plan_view(view):
        _show_message(
            constants.WINDOW_TITLE,
            "Activate a plan view before running this tool.",
            "Floor, ceiling, area, and structural plan views are supported.",
        )
        return None, None, None

    if getattr(view, "IsTemplate", False):
        _show_message(
            constants.WINDOW_TITLE,
            "Activate a real plan view, not a view template.",
        )
        return None, None, None

    return uidoc, doc, view


def _is_plan_view(view):
    if view is None or not isinstance(view, View):
        return False
    try:
        return view.ViewType in _PLAN_VIEW_TYPES
    except Exception:
        return False


def _report_instruction(report):
    if report.dry_run:
        return "Auto Dimension preview finished."
    if report.success:
        return "Auto Dimension finished."
    return "Auto Dimension finished with no dimensions created."


def _format_report(report):
    created_label = "would create" if report.dry_run else "created"
    lines = []
    if report.dry_run:
        lines.append("Dry Run Preview")
        lines.append("")
    lines.append(report.message or "Finished.")
    lines.append("")
    lines.append("Summary:")
    for outcome in report.outcomes:
        lines.append("  - {0}: {1} {2}, {3} skipped".format(
            outcome.label,
            outcome.created_count,
            created_label,
            len(outcome.skipped_items),
        ))
        for note in outcome.notes:
            lines.append("      note: {0}".format(note))

    skipped = report.all_skipped()
    if skipped:
        lines.append("")
        lines.append("Skipped items ({0}):".format(len(skipped)))
        for item in skipped:
            lines.append("  - {0} #{1}: {2}".format(
                item.category,
                item.element_id,
                item.reason,
            ))
    else:
        lines.append("")
        lines.append("Skipped items: none")
    return "\n".join(lines)


def _print_output_report(report):
    if pyrevit_script is None:
        return
    try:
        output = pyrevit_script.get_output()
    except Exception:
        return

    created_label = "Would create" if report.dry_run else "Created"
    try:
        output.print_md("# Auto Dimension")
        output.print_md("**Result:** {0}".format(report.message or "Finished."))
        output.print_md("**Dry Run:** {0}".format("Yes" if report.dry_run else "No"))
        output.print_md("")
        output.print_md("## Summary")
        for outcome in report.outcomes:
            output.print_md("- **{0}:** {1} {2}, {3} skipped".format(
                outcome.label,
                outcome.created_count,
                created_label.lower(),
                len(outcome.skipped_items),
            ))
            for note in outcome.notes:
                output.print_md("  - {0}".format(note))
        skipped = report.all_skipped()
        if skipped:
            output.print_md("")
            output.print_md("## Skipped")
            for item in skipped:
                output.print_md("- {0} #{1}: {2}".format(
                    item.category,
                    item.element_id,
                    item.reason,
                ))
    except Exception:
        pass


def _show_message(title, instruction, content=""):
    dialog = TaskDialog(title)
    dialog.MainInstruction = instruction
    if content:
        dialog.MainContent = content
    dialog.CommonButtons = TaskDialogCommonButtons.Ok
    try:
        dialog.FooterText = "All Rights Reserved (c) Ajmal P.S. | AJ Tools"
    except Exception:
        pass
    dialog.Show()


if __name__ == "__main__":
    main()
