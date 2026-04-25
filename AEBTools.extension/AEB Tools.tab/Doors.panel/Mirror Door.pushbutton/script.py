# -*- coding: utf-8 -*-
"""
Tool Name    : Mirror Door
Purpose      : Find mirrored and unmirrored host-document door instances using the real FamilyInstance.Mirrored property
Author       : Ajmal P.S.
Company      : AEB Tools
Version      : 1.2.4
Created      : 2026-04-22
Last Updated : 2026-04-25
Target       : Revit 2020-2027
Platform     : pyRevit / Python
Dependencies : Autodesk Revit API, pyRevit
Input        : Active Revit project document and user-selected scope
Output       : Single-window mirrored door workflow with scan, selection, and Excel-compatible CSV export
Notes        : Keeps the full workflow inside one result window with scan, selection, and export actions
Changelog    : v1.2.4 - Aligned metadata, naming, and release assets with the maintained workflow
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from __future__ import absolute_import, division, print_function

import codecs
import os
from datetime import datetime

from Autodesk.Revit.UI import TaskDialog, TaskDialogCommonButtons
from pyrevit import forms, script

from common import mirrored_doors as engine
from common import ui_branding


logger = script.get_logger()

EXPORT_DIALOG_TITLE = "Export Mirror Door Report"
EXPORT_DIALOG_FILTER = "CSV Files (*.csv)|*.csv"


class UiOption(object):
    def __init__(self, key, display_name):
        self.key = key
        self.display_name = display_name


class DoorGridRow(object):
    def __init__(self, record):
        self.record = record
        self.element_id = record.element_id
        self.family_name = or_unavailable(record.family_name)
        self.type_name = or_unavailable(record.type_name)
        self.level_name = or_unavailable(record.level_name)
        self.mark = or_unavailable(record.mark)
        self.room_number = or_unavailable(record.room_number)
        self.room_name = or_unavailable(record.room_name)
        self.host_label = or_unavailable(record.host_label)
        self.mirrored_status = "Mirrored" if record.is_mirrored else "Unmirrored"


class MirrorDoorWindow(forms.WPFWindow):
    def __init__(self, doc, uidoc):
        self.doc = doc
        self.uidoc = uidoc
        self.scan_result = None
        self.mirrored_rows = []
        self.unmirrored_rows = []

        xaml_path = os.path.join(os.path.dirname(__file__), "ui.xaml")
        forms.WPFWindow.__init__(self, xaml_path, handle_esc=True)
        ui_branding.apply_window_footer(self)

        self.scope_options = [
            UiOption(engine.SCOPE_WHOLE_PROJECT, "Whole Project"),
            UiOption(engine.SCOPE_ACTIVE_VIEW, "Active View"),
            UiOption(engine.SCOPE_CURRENT_SELECTION, "Selected Elements"),
        ]

        self.scopeComboBox.ItemsSource = self.scope_options
        self.scopeComboBox.DisplayMemberPath = "display_name"
        self.scopeComboBox.SelectedItem = self.scope_options[0]

        self.mirroredDataGrid.ItemsSource = self.mirrored_rows
        self.unmirroredDataGrid.ItemsSource = self.unmirrored_rows

        self.reset_results("Select a scope and click Scan.")

    def on_scope_changed(self, sender, args):  # pylint: disable=unused-argument
        self.reset_results("Scope changed. Click Scan to refresh results.")

    def on_scan_click(self, sender, args):  # pylint: disable=unused-argument
        scope_key = self.get_selected_scope_key()
        self.scan_result = engine.inspect_scope(
            doc=self.doc,
            uidoc=self.uidoc,
            active_view=getattr(self.doc, "ActiveView", None),
            scope_key=scope_key,
        )
        self.load_results()

    def on_select_mirrored_click(self, sender, args):  # pylint: disable=unused-argument
        if self.scan_result is None:
            self.set_status("Scan a scope before selecting doors in the model.")
            return

        rows = self.get_rows_for_category(self.mirroredDataGrid, self.mirrored_rows)
        records = self.rows_to_records(rows)
        _, message = engine.select_records(self.uidoc, records)
        self.set_status(message)

    def on_select_unmirrored_click(self, sender, args):  # pylint: disable=unused-argument
        if self.scan_result is None:
            self.set_status("Scan a scope before selecting doors in the model.")
            return

        rows = self.get_rows_for_category(self.unmirroredDataGrid, self.unmirrored_rows)
        records = self.rows_to_records(rows)
        _, message = engine.select_records(self.uidoc, records)
        self.set_status(message)

    def on_export_report_click(self, sender, args):  # pylint: disable=unused-argument
        if self.scan_result is None:
            self.set_status("Scan a scope before exporting the report.")
            return

        success, message = export_report_to_excel_compatible_csv(self.scan_result)
        self.set_status(message)
        if success:
            logger.info(message)

    def on_close_click(self, sender, args):  # pylint: disable=unused-argument
        self.Close()

    def get_selected_scope_key(self):
        selected_item = self.scopeComboBox.SelectedItem
        if selected_item is None:
            return engine.SCOPE_WHOLE_PROJECT
        return selected_item.key

    def reset_results(self, status_message):
        self.scan_result = None
        self.mirrored_rows = []
        self.unmirrored_rows = []
        self.mirroredDataGrid.ItemsSource = self.mirrored_rows
        self.unmirroredDataGrid.ItemsSource = self.unmirrored_rows
        self.scopeValueTextBlock.Text = get_selected_scope_display_name(self.scopeComboBox.SelectedItem)
        self.totalDoorsValueTextBlock.Text = "0"
        self.mirroredDoorsValueTextBlock.Text = "0"
        self.unmirroredDoorsValueTextBlock.Text = "0"
        self.skippedDoorsValueTextBlock.Text = "0"
        self.mirroredHeaderTextBlock.Text = "Mirrored Doors (0)"
        self.unmirroredHeaderTextBlock.Text = "Unmirrored Doors (0)"
        self.summaryNoteTextBlock.Text = "Scan results will appear here."
        self.set_status(status_message)

    def load_results(self):
        self.mirrored_rows = [DoorGridRow(record) for record in self.scan_result.mirrored_records]
        self.unmirrored_rows = [DoorGridRow(record) for record in self.scan_result.non_mirrored_records]

        self.mirroredDataGrid.ItemsSource = self.mirrored_rows
        self.unmirroredDataGrid.ItemsSource = self.unmirrored_rows

        self.scopeValueTextBlock.Text = self.scan_result.scope_label
        self.totalDoorsValueTextBlock.Text = text_value(self.scan_result.total_doors)
        self.mirroredDoorsValueTextBlock.Text = text_value(self.scan_result.mirrored_count)
        self.unmirroredDoorsValueTextBlock.Text = text_value(self.scan_result.non_mirrored_count)
        self.skippedDoorsValueTextBlock.Text = text_value(self.scan_result.skipped_count)
        self.mirroredHeaderTextBlock.Text = "Mirrored Doors ({0})".format(self.scan_result.mirrored_count)
        self.unmirroredHeaderTextBlock.Text = "Unmirrored Doors ({0})".format(self.scan_result.non_mirrored_count)
        self.summaryNoteTextBlock.Text = build_result_note_text(self.scan_result)
        self.set_status(build_scan_status_text(self.scan_result))

    def get_rows_for_category(self, data_grid, fallback_rows):
        selected_rows = self.get_selected_rows(data_grid)
        if selected_rows:
            return selected_rows
        return list(fallback_rows)

    def get_selected_rows(self, data_grid):
        try:
            return list(data_grid.SelectedItems)
        except Exception:
            selected_item = getattr(data_grid, "SelectedItem", None)
            if selected_item is None:
                return []
            return [selected_item]

    def rows_to_records(self, rows):
        records = []
        seen_ids = set()
        for row in rows:
            record = getattr(row, "record", None)
            if record is None:
                continue
            record_id = getattr(record, "element_id", None)
            if record_id in seen_ids:
                continue
            records.append(record)
            seen_ids.add(record_id)
        return records

    def refresh_action_button_state(self):
        has_scan_result = self.scan_result is not None
        self.selectMirroredButton.IsEnabled = has_scan_result and bool(self.mirrored_rows)
        self.selectUnmirroredButton.IsEnabled = has_scan_result and bool(self.unmirrored_rows)
        self.exportReportButton.IsEnabled = has_scan_result

    def set_status(self, message):
        self.resultStatusTextBlock.Text = message or ""
        self.refresh_action_button_state()


def main():
    uidoc = getattr(__revit__, "ActiveUIDocument", None)
    if uidoc is None:
        show_message_dialog("Open a Revit project document before running this tool.")
        return

    doc = uidoc.Document
    if doc is None:
        show_message_dialog("No active Revit document was found.")
        return

    if getattr(doc, "IsFamilyDocument", False):
        show_message_dialog("Open a Revit project document before running this tool.")
        return

    window = MirrorDoorWindow(doc, uidoc)
    window.show_dialog()


def export_report_to_excel_compatible_csv(scan_result):
    file_path, error_message = prompt_for_export_file_path()
    if error_message:
        return False, error_message

    if not file_path:
        return False, "Export canceled."

    try:
        write_csv_report(file_path, scan_result)
        return True, "Excel-compatible CSV exported to: {0}".format(file_path)
    except Exception as export_error:
        return False, "Export failed: {0}".format(engine.clean_exception_message(export_error))


def prompt_for_export_file_path():
    wpf_path, wpf_error = prompt_for_export_file_path_wpf()
    if wpf_path:
        return wpf_path, None

    winforms_path, winforms_error = prompt_for_export_file_path_winforms()
    if winforms_path:
        return winforms_path, None

    if wpf_error and winforms_error:
        return None, "Export failed: {0} | {1}".format(wpf_error, winforms_error)
    return None, wpf_error or winforms_error


def prompt_for_export_file_path_wpf():
    try:
        import clr
        clr.AddReference("PresentationFramework")
        from Microsoft.Win32 import SaveFileDialog

        dialog = SaveFileDialog()
        dialog.Title = EXPORT_DIALOG_TITLE
        dialog.Filter = EXPORT_DIALOG_FILTER
        dialog.DefaultExt = ".csv"
        dialog.AddExtension = True
        dialog.OverwritePrompt = True
        dialog.FileName = build_default_export_name()

        dialog_result = dialog.ShowDialog()
        if dialog_result == True:
            return dialog.FileName, None
        return None, None
    except Exception as dialog_error:
        return None, engine.clean_exception_message(dialog_error)


def prompt_for_export_file_path_winforms():
    dialog = None
    try:
        import clr
        clr.AddReference("System.Windows.Forms")
        from System.Windows.Forms import DialogResult, SaveFileDialog

        dialog = SaveFileDialog()
        dialog.Title = EXPORT_DIALOG_TITLE
        dialog.Filter = EXPORT_DIALOG_FILTER
        dialog.DefaultExt = "csv"
        dialog.AddExtension = True
        dialog.OverwritePrompt = True
        dialog.FileName = build_default_export_name()

        dialog_result = dialog.ShowDialog()
        if dialog_result == DialogResult.OK:
            return dialog.FileName, None
        return None, None
    except Exception as dialog_error:
        return None, engine.clean_exception_message(dialog_error)
    finally:
        if dialog is not None:
            try:
                dialog.Dispose()
            except Exception:
                pass


def write_csv_report(file_path, scan_result):
    lines = []
    append_csv_row(lines, ["Section", "Label", "Value"])
    append_csv_row(lines, ["Summary", "Scope", scan_result.scope_label])
    append_csv_row(lines, ["Summary", "Total doors checked", scan_result.total_doors])
    append_csv_row(lines, ["Summary", "Total mirrored doors", scan_result.mirrored_count])
    append_csv_row(lines, ["Summary", "Total unmirrored doors", scan_result.non_mirrored_count])
    append_csv_row(lines, ["Summary", "Total skipped doors", scan_result.skipped_count])
    append_csv_row(lines, ["Summary", "Grouped doors in scope", scan_result.grouped_door_count])
    append_csv_row(lines, ["Summary", "Grouped mirrored doors", scan_result.grouped_mirrored_count])

    if scan_result.collection_note:
        append_csv_row(lines, ["Summary", "Scope note", scan_result.collection_note])

    append_blank_csv_row(lines)
    append_detail_table(lines, "Mirrored Doors", scan_result.mirrored_records)
    append_blank_csv_row(lines)
    append_detail_table(lines, "Unmirrored Doors", scan_result.non_mirrored_records)

    if scan_result.skipped_records:
        append_blank_csv_row(lines)
        append_csv_row(lines, ["Skipped Doors"])
        append_csv_row(lines, ["Element ID", "Reason"])
        for skipped in scan_result.skipped_records:
            append_csv_row(lines, [skipped.element_id, skipped.reason])

    with codecs.open(file_path, "w", "utf-8-sig") as export_file:
        export_file.write("\r\n".join(lines))


def append_detail_table(lines, section_title, records):
    append_csv_row(lines, [section_title])
    append_csv_row(
        lines,
        [
            "Element ID",
            "Family Name",
            "Type Name",
            "Level",
            "Mark",
            "Room Number",
            "Room Name",
            "Host",
            "Mirrored Status",
            "Notes",
        ],
    )

    if not records:
        append_csv_row(lines, ["", "No records"])
        return

    for record in records:
        append_csv_row(
            lines,
            [
                record.element_id,
                or_unavailable(record.family_name),
                or_unavailable(record.type_name),
                or_unavailable(record.level_name),
                or_unavailable(record.mark),
                or_unavailable(record.room_number),
                or_unavailable(record.room_name),
                or_unavailable(record.host_label),
                "Mirrored" if record.is_mirrored else "Unmirrored",
                "; ".join(record.notes) if record.notes else "",
            ],
        )


def append_blank_csv_row(lines):
    lines.append("")


def append_csv_row(lines, values):
    lines.append(",".join(escape_csv_value(value) for value in values))


def escape_csv_value(value):
    text_value = engine.safe_text(value)
    if any(marker in text_value for marker in [",", "\"", "\r", "\n"]):
        text_value = "\"{0}\"".format(text_value.replace("\"", "\"\""))
    return text_value


def build_default_export_name():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return "mirror_door_report_{0}.csv".format(timestamp)


def build_scan_status_text(scan_result):
    if scan_result.total_doors <= 0:
        return "No host-document door instances were found in the selected scope."

    if scan_result.mirrored_count:
        return "{0} mirrored door(s) found. Select rows and use the action buttons below.".format(
            scan_result.mirrored_count
        )

    return "Scan completed. No mirrored doors were found in the selected scope."


def build_result_note_text(scan_result):
    lines = [
        "Host model only: {0}".format(scan_result.host_only_note),
        "Select Mirrored in Model and Select Unmirrored in Model use the selected rows from that list. If nothing is selected in that list, the full list is used.",
        "Export Full Report to Excel writes an Excel-compatible CSV file to avoid external dependencies.",
    ]

    if scan_result.collection_note:
        lines.append("Scope note: {0}".format(scan_result.collection_note))

    return "\n".join(lines)


def get_selected_scope_display_name(selected_item):
    if selected_item is None:
        return engine.get_scope_label(engine.SCOPE_WHOLE_PROJECT)
    return selected_item.display_name


def show_message_dialog(message, instruction=None):
    dialog = TaskDialog("Mirror Door")
    dialog.MainInstruction = instruction or message
    dialog.MainContent = "" if instruction is None else message
    dialog.CommonButtons = TaskDialogCommonButtons.Ok
    ui_branding.apply_task_dialog_footer(dialog)
    dialog.Show()


def text_value(value):
    return str(value)


def or_unavailable(value):
    return value if value else "Unavailable"


if __name__ == "__main__":
    main()
