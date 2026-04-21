# -*- coding: utf-8 -*-
"""
Tool Name    : Room to Door
Purpose      : Launch the door parameter UI and write values from associated room numbers
Author       : Ajmal P.S.
Company      : AJ Tools
Version      : 1.0.1
Created      : 2026-04-21
Last Updated : 2026-04-21
Target       : Revit 2020-2027
Platform     : pyRevit / Python
Dependencies : Autodesk Revit API, pyRevit
Input        : Doors, Rooms, User UI settings
Output       : Updated door parameter values and command feedback
Notes        : Supports active view, current selection, and whole project scopes with suffix options and branded UI footers
Changelog    : v1.0.1 - Added branded footer text to custom and task dialog UI
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from __future__ import absolute_import, division, print_function

import os

from Autodesk.Revit.UI import (
    TaskDialog,
    TaskDialogCommonButtons,
    TaskDialogResult,
)
from pyrevit import forms, script

from common import door_room_numbering as engine
from common import ui_branding


logger = script.get_logger()
output = script.get_output()


class UiOption(object):
    def __init__(self, key, display_name):
        self.key = key
        self.display_name = display_name


class DoorParameterFromRoomNumberWindow(forms.WPFWindow):
    def __init__(self, doc, uidoc):
        self.doc = doc
        self.uidoc = uidoc
        self.active_view = getattr(doc, "ActiveView", None)
        self.scope_cache = {}
        self.preview_result = None
        self._is_initializing = True

        xaml_path = os.path.join(os.path.dirname(__file__), "ui.xaml")
        forms.WPFWindow.__init__(self, xaml_path, handle_esc=True)
        ui_branding.apply_window_footer(self)

        self.scope_options = [
            UiOption(engine.SCOPE_ACTIVE_VIEW, "Active View Only"),
            UiOption(engine.SCOPE_CURRENT_SELECTION, "Current Selection Only"),
            UiOption(engine.SCOPE_WHOLE_PROJECT, "Whole Project"),
        ]

        self.scopeComboBox.ItemsSource = self.scope_options
        self.scopeComboBox.DisplayMemberPath = "display_name"
        self.scopeComboBox.SelectedItem = self.scope_options[2]

        self.parameterComboBox.DisplayMemberPath = "display_name"
        self.alphabeticRadioButton.IsChecked = True
        self.separatorTextBox.Text = "-"
        self.noSuffixSingleCheckBox.IsChecked = True
        self.overwriteExistingCheckBox.IsChecked = False

        self._is_initializing = False
        self.refresh_scope_state()

    def on_scope_changed(self, sender, args):  # pylint: disable=unused-argument
        if self._is_initializing:
            return
        self.refresh_scope_state()

    def on_settings_changed(self, sender, args):  # pylint: disable=unused-argument
        if self._is_initializing:
            return
        self.update_preview()

    def on_run_click(self, sender, args):  # pylint: disable=unused-argument
        preview = self.update_preview()
        if preview is None:
            return

        if preview.blocking_message:
            show_message_dialog(preview.blocking_message, "Action required before update.")
            return

        if not preview.update_items:
            show_message_dialog(
                "No eligible door values need updating with the current settings.",
                "Nothing to update.",
            )
            return

        if not confirm_preview(preview):
            return

        self.preview_result = preview
        try:
            self.DialogResult = True
        except Exception:
            pass
        self.Close()

    def on_cancel_click(self, sender, args):  # pylint: disable=unused-argument
        self.preview_result = None
        self.Close()

    def refresh_scope_state(self):
        scope_key = self.get_selected_scope_key()
        if scope_key in self.scope_cache:
            scope_state = self.scope_cache[scope_key]
        else:
            scope_state = engine.analyze_scope(
                doc=self.doc,
                uidoc=self.uidoc,
                active_view=self.active_view,
                scope_key=scope_key,
            )
            self.scope_cache[scope_key] = scope_state

        previous_parameter_key = self.get_selected_parameter_key()
        parameter_choices = list(scope_state.parameter_choices)
        self.parameterComboBox.ItemsSource = parameter_choices
        self.parameterComboBox.IsEnabled = bool(parameter_choices)

        selected_index = -1
        for index, parameter_choice in enumerate(parameter_choices):
            if parameter_choice.key == previous_parameter_key:
                selected_index = index
                break

        if selected_index >= 0:
            self.parameterComboBox.SelectedItem = parameter_choices[selected_index]
        elif parameter_choices:
            self.parameterComboBox.SelectedItem = parameter_choices[0]
        else:
            self.parameterComboBox.SelectedIndex = -1

        self.update_preview()

    def update_preview(self):
        scope_state = self.scope_cache.get(self.get_selected_scope_key())
        if scope_state is None:
            self.previewTextBox.Text = "No scope analysis is available."
            self.statusTextBlock.Text = ""
            self.runButton.IsEnabled = False
            return None

        preview = engine.build_preview(
            scope_state=scope_state,
            parameter_key=self.get_selected_parameter_key(),
            suffix_mode=self.get_suffix_mode(),
            separator=self.get_separator(),
            no_suffix_single=self.get_no_suffix_single(),
            overwrite_existing=self.get_overwrite_existing(),
        )

        self.previewTextBox.Text = build_preview_text(preview)
        self.statusTextBlock.Text = build_status_text(preview)
        self.runButton.IsEnabled = not preview.blocking_message and bool(preview.update_items)
        return preview

    def get_selected_scope_key(self):
        selected_item = self.scopeComboBox.SelectedItem
        if selected_item is None:
            return engine.SCOPE_WHOLE_PROJECT
        return selected_item.key

    def get_selected_parameter_key(self):
        selected_item = self.parameterComboBox.SelectedItem
        if selected_item is None:
            return None
        return selected_item.key

    def get_suffix_mode(self):
        if self.numericRadioButton.IsChecked:
            return engine.SUFFIX_NUMERIC
        return engine.SUFFIX_ALPHABETIC

    def get_separator(self):
        return self.separatorTextBox.Text or ""

    def get_no_suffix_single(self):
        return bool(self.noSuffixSingleCheckBox.IsChecked)

    def get_overwrite_existing(self):
        return bool(self.overwriteExistingCheckBox.IsChecked)


def main():
    uidoc = getattr(__revit__, "ActiveUIDocument", None)
    if uidoc is None:
        show_message_dialog("Open a Revit project document before running this tool.")
        return

    doc = uidoc.Document
    if doc is None:
        show_message_dialog("No active Revit document was found.")
        return

    window = DoorParameterFromRoomNumberWindow(doc, uidoc)
    window.show_dialog()

    preview = window.preview_result
    if preview is None:
        logger.info("Room to Door cancelled by user.")
        return

    result = engine.execute_write_plan(doc, preview)
    print_report(preview, result)
    show_result_dialog(result)


def build_preview_text(preview):
    parameter_name = "(none selected)"
    if preview.parameter_choice is not None:
        parameter_name = preview.parameter_choice.name

    lines = [
        "Scope: {0}".format(preview.scope_state.scope_label),
        "Total doors found: {0}".format(preview.total_doors),
        "Resolved door-room assignments: {0}".format(preview.resolved_door_count),
        "Room number groups: {0}".format(preview.room_group_count),
        "Text parameters scanned: {0}".format(preview.scope_state.string_parameter_instance_count),
        "Writable text parameters scanned: {0}".format(preview.scope_state.writable_string_parameter_instance_count),
        "Writable parameter options: {0}".format(len(preview.scope_state.parameter_choices)),
        "Doors to update: {0}".format(len(preview.update_items)),
        "Doors skipped: {0}".format(len(preview.skipped_items)),
        "Selected parameter: {0}".format(parameter_name),
        "Suffix mode: {0}".format(format_suffix_mode(preview.suffix_mode)),
        "Separator: {0}".format(format_separator(preview.separator)),
        "No suffix for single door: {0}".format(format_yes_no(preview.no_suffix_single)),
        "Overwrite existing values: {0}".format(format_yes_no(preview.overwrite_existing)),
    ]

    if preview.scope_state.collection_note:
        lines.append("Scope note: {0}".format(preview.scope_state.collection_note))

    lines.append("Linked-model doors are not edited; only host-document doors in the chosen scope are processed.")

    if preview.scope_state.grouped_door_count:
        lines.append(
            "Grouped doors in scope: {0}. Group member writes can still fail if the selected parameter cannot vary by group.".format(
                preview.scope_state.grouped_door_count
            )
        )

    if preview.blocking_message:
        lines.append("Action required: {0}".format(preview.blocking_message))
    elif not preview.update_items:
        lines.append("Nothing is queued for writing with the current settings.")

    return "\n".join(lines)


def build_status_text(preview):
    parameter_count = len(preview.scope_state.parameter_choices)
    if preview.blocking_message:
        return preview.blocking_message

    return "{0} parameter option(s) available. {1} door(s) ready to update.".format(
        parameter_count,
        len(preview.update_items),
    )


def confirm_preview(preview):
    dialog = TaskDialog("Room to Door")
    dialog.MainInstruction = "Review preview and update the selected door parameter?"
    dialog.MainContent = (
        "Scope: {0}\n"
        "Parameter: {1}\n"
        "Suffix mode: {2}\n"
        "Separator: {3}\n"
        "Doors to update: {4}\n"
        "Doors skipped: {5}".format(
            preview.scope_state.scope_label,
            preview.parameter_choice.name,
            format_suffix_mode(preview.suffix_mode),
            format_separator(preview.separator),
            len(preview.update_items),
            len(preview.skipped_items),
        )
    )
    dialog.CommonButtons = TaskDialogCommonButtons.Ok | TaskDialogCommonButtons.Cancel
    ui_branding.apply_task_dialog_footer(dialog)
    return dialog.Show() == TaskDialogResult.Ok


def show_message_dialog(message, instruction=None):
    dialog = TaskDialog("Room to Door")
    dialog.MainInstruction = instruction or message
    dialog.MainContent = "" if instruction is None else message
    dialog.CommonButtons = TaskDialogCommonButtons.Ok
    ui_branding.apply_task_dialog_footer(dialog)
    dialog.Show()


def show_result_dialog(result):
    dialog = TaskDialog("Room to Door")
    dialog.MainInstruction = "Door parameter update completed."
    dialog.MainContent = (
        "Updated: {0}\n"
        "Skipped: {1}\n"
        "Failed: {2}\n\n"
        "Detailed reporting has been written to the pyRevit output panel.".format(
            len(result.updated_items),
            len(result.skipped_items),
            len(result.failed_items),
        )
    )
    dialog.CommonButtons = TaskDialogCommonButtons.Ok
    ui_branding.apply_task_dialog_footer(dialog)
    dialog.Show()


def print_report(preview, result):
    output.print_md("# Room to Door")
    output.print_md("**Scope:** {0}".format(preview.scope_state.scope_label))
    output.print_md("**Parameter:** {0}".format(preview.parameter_choice.name))
    output.print_md("**Suffix Mode:** {0}".format(format_suffix_mode(preview.suffix_mode)))
    output.print_md("**Separator:** {0}".format(format_separator(preview.separator)))
    output.print_md("**No Suffix For Single Door:** {0}".format(format_yes_no(preview.no_suffix_single)))
    output.print_md("**Overwrite Existing Values:** {0}".format(format_yes_no(preview.overwrite_existing)))
    output.print_md("")
    output.print_md("## Summary")
    output.print_md("- Updated: {0}".format(len(result.updated_items)))
    output.print_md("- Skipped: {0}".format(len(result.skipped_items)))
    output.print_md("- Failed: {0}".format(len(result.failed_items)))

    if result.updated_items:
        output.print_md("")
        output.print_md("## Updated Doors")
        for item in sorted(result.updated_items, key=lambda update: update.door_record.sort_key):
            output.print_md(
                "- {0} -> `{1}`".format(item.door_record.door_label, item.target_value)
            )

    if result.skipped_items:
        output.print_md("")
        output.print_md("## Skipped Doors")
        for issue in sorted(result.skipped_items, key=lambda value: value.door_record.sort_key):
            output.print_md("- {0}: {1}".format(issue.door_record.door_label, issue.reason))

    if result.failed_items:
        output.print_md("")
        output.print_md("## Failed Writes")
        for issue in sorted(result.failed_items, key=lambda value: value.door_record.sort_key):
            if issue.target_value:
                output.print_md(
                    "- {0}: {1} Target value: `{2}`".format(
                        issue.door_record.door_label,
                        issue.reason,
                        issue.target_value,
                    )
                )
            else:
                output.print_md("- {0}: {1}".format(issue.door_record.door_label, issue.reason))


def format_separator(value):
    if value:
        return "'{0}'".format(value)
    return "(blank)"


def format_suffix_mode(value):
    if value == engine.SUFFIX_NUMERIC:
        return "Numeric"
    return "Alphabetic"


def format_yes_no(value):
    return "Yes" if value else "No"


if __name__ == "__main__":
    main()
