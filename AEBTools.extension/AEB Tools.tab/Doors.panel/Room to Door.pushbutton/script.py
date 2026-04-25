# -*- coding: utf-8 -*-
"""
Tool Name    : Room to Door
Purpose      : Launch the door parameter UI and write room-number door values with stable suffixing
Author       : Ajmal P.S.
Company      : AEB Tools
Version      : 1.0.1
Created      : 2026-04-25
Last Updated : 2026-04-25
Target       : Revit 2020-2027
Platform     : pyRevit / IronPython
Dependencies : Autodesk Revit API, pyRevit
Input        : Doors, Rooms, User UI settings
Output       : Updated door parameter values and command feedback
Notes        : Supports active view, current selection, and whole project scopes with stable room-number suffix options
Changelog    : v1.0.1 - Cleaner preview, simpler UI, stale-selection refresh, removed dead code
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from __future__ import absolute_import, division, print_function

__title__ = "Room to Door"
__author__ = "Ajmal P.S."
__doc__ = "Write room numbers to door parameters using stable facing-side and opposite-side detection."

import os
from collections import Counter

from Autodesk.Revit.UI import (
    TaskDialog,
    TaskDialogCommonButtons,
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


class RoomToDoorWindow(forms.WPFWindow):
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
            UiOption(engine.SCOPE_CURRENT_SELECTION, engine.get_scope_label(engine.SCOPE_CURRENT_SELECTION)),
            UiOption(engine.SCOPE_ACTIVE_VIEW, engine.get_scope_label(engine.SCOPE_ACTIVE_VIEW)),
            UiOption(engine.SCOPE_WHOLE_PROJECT, engine.get_scope_label(engine.SCOPE_WHOLE_PROJECT)),
        ]
        self.room_side_options = [
            UiOption(engine.ROOM_SIDE_FACING, engine.get_room_side_label(engine.ROOM_SIDE_FACING)),
            UiOption(engine.ROOM_SIDE_OPPOSITE, engine.get_room_side_label(engine.ROOM_SIDE_OPPOSITE)),
        ]

        self.scopeComboBox.ItemsSource = self.scope_options
        self.scopeComboBox.DisplayMemberPath = "display_name"
        self.scopeComboBox.SelectedItem = self.scope_options[2]

        self.roomSideComboBox.ItemsSource = self.room_side_options
        self.roomSideComboBox.DisplayMemberPath = "display_name"
        self.roomSideComboBox.SelectedItem = self.room_side_options[0]

        self.parameterComboBox.DisplayMemberPath = "display_name"
        self.suffixCheckBox.IsChecked = True
        self.numericRadioButton.IsChecked = True
        self.separatorTextBox.Text = "-"
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
        self.refresh_suffix_state()
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
        cache_key = self.get_scope_cache_key()

        # Selection scope is re-analyzed on each visit so a changed Revit
        # selection is picked up without closing and reopening the tool.
        if scope_key == engine.SCOPE_CURRENT_SELECTION or cache_key not in self.scope_cache:
            scope_state = engine.analyze_scope(
                doc=self.doc,
                uidoc=self.uidoc,
                active_view=self.active_view,
                scope_key=scope_key,
            )
            self.scope_cache[cache_key] = scope_state
        else:
            scope_state = self.scope_cache[cache_key]

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

        self.refresh_suffix_state()
        self.update_preview()

    def update_preview(self):
        scope_state = self.scope_cache.get(self.get_scope_cache_key())
        if scope_state is None:
            self.previewTextBox.Text = "No scope analysis is available."
            self.statusTextBlock.Text = ""
            self.runButton.IsEnabled = False
            return None

        preview = engine.build_preview(
            scope_state=scope_state,
            parameter_key=self.get_selected_parameter_key(),
            room_side_key=self.get_selected_room_side_key(),
            suffix_enabled=self.get_suffix_enabled(),
            suffix_mode=self.get_selected_suffix_mode(),
            separator=self.get_separator(),
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

    def get_scope_cache_key(self):
        return self.get_selected_scope_key()

    def get_selected_room_side_key(self):
        selected_item = self.roomSideComboBox.SelectedItem
        if selected_item is None:
            return engine.ROOM_SIDE_FACING
        return selected_item.key

    def get_selected_parameter_key(self):
        selected_item = self.parameterComboBox.SelectedItem
        if selected_item is None:
            return None
        return selected_item.key

    def get_suffix_enabled(self):
        return bool(self.suffixCheckBox.IsChecked)

    def get_selected_suffix_mode(self):
        if self.alphabeticRadioButton.IsChecked:
            return engine.SUFFIX_ALPHABETIC
        return engine.SUFFIX_NUMERIC

    def get_separator(self):
        return self.separatorTextBox.Text or ""

    def get_overwrite_existing(self):
        return bool(self.overwriteExistingCheckBox.IsChecked)

    def refresh_suffix_state(self):
        suffix_enabled = self.get_suffix_enabled()
        self.numericRadioButton.IsEnabled = suffix_enabled
        self.alphabeticRadioButton.IsEnabled = suffix_enabled
        self.separatorTextBox.IsEnabled = suffix_enabled


def main():
    uidoc = getattr(__revit__, "ActiveUIDocument", None)
    if uidoc is None:
        show_message_dialog("Open a Revit project document before running this tool.")
        return

    doc = uidoc.Document
    if doc is None:
        show_message_dialog("No active Revit document was found.")
        return

    window = RoomToDoorWindow(doc, uidoc)
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

    side_label = engine.get_room_side_label(preview.room_side_key)
    lines = [
        "Scope:          {0}".format(preview.scope_state.scope_label),
        "Doors found:    {0}".format(preview.total_doors),
        "Rooms resolved: {0} of {1} on the {2}".format(
            preview.selected_side_resolved_count,
            preview.total_doors,
            side_label.lower(),
        ),
        "",
        "Parameter:      {0}".format(parameter_name),
        "Room side:      {0}".format(side_label),
        "Suffix:         {0}".format(format_suffix_summary(preview)),
        "Overwrite:      {0}".format(format_yes_no(preview.overwrite_existing)),
        "",
        "Doors to update: {0}".format(len(preview.update_items)),
        "Doors skipped:   {0}".format(len(preview.skipped_items)),
    ]

    if preview.multi_door_room_count > 0:
        lines.append(
            "Rooms with multiple doors on this side: {0}".format(preview.multi_door_room_count)
        )

    if preview.accessor_fallback_count > 0:
        lines.append(
            "Doors resolved via ToRoom/FromRoom fallback: {0}".format(preview.accessor_fallback_count)
        )

    if preview.scope_state.grouped_door_count:
        lines.append(
            "Grouped doors in scope: {0} (Revit may block writes for grouped instances).".format(
                preview.scope_state.grouped_door_count
            )
        )

    if preview.scope_state.collection_note:
        lines.append("")
        lines.append("Note: {0}".format(preview.scope_state.collection_note))

    append_skip_reason_summary(lines, preview.skipped_items)

    if preview.blocking_message:
        lines.append("")
        lines.append("Action required: {0}".format(preview.blocking_message))
    elif not preview.update_items:
        lines.append("")
        lines.append("Nothing to update with the current settings.")

    return "\n".join(lines)


def build_status_text(preview):
    if preview.blocking_message:
        return preview.blocking_message

    parameter_count = len(preview.scope_state.parameter_choices)
    return "{0} parameter option(s) available. {1} door(s) ready to update.".format(
        parameter_count,
        len(preview.update_items),
    )


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
    output.print_md("**Room Side:** {0}".format(engine.get_room_side_label(preview.room_side_key)))
    output.print_md("**Suffix:** {0}".format(format_suffix_summary(preview)))
    output.print_md("**Overwrite Existing Values:** {0}".format(format_yes_no(preview.overwrite_existing)))
    output.print_md("")
    output.print_md("## Summary")
    output.print_md("- Updated: {0}".format(len(result.updated_items)))
    output.print_md("- Skipped: {0}".format(len(result.skipped_items)))
    output.print_md("- Failed: {0}".format(len(result.failed_items)))

    if result.updated_items:
        output.print_md("")
        output.print_md("## Updated Doors")
        for item in sorted(result.updated_items, key=get_result_item_sort_key):
            output.print_md(
                "- {0} -> `{1}` ({2}) | {3}".format(
                    item.door_record.door_label,
                    item.target_value,
                    item.room_match.source_label,
                    format_door_side_details(item.door_record),
                )
            )

    if result.skipped_items:
        output.print_md("")
        output.print_md("## Skipped Doors")
        for issue in sorted(result.skipped_items, key=lambda value: get_issue_sort_key(value, preview.room_side_key)):
            output.print_md(
                "- {0}: {1} | {2}".format(
                    issue.door_record.door_label,
                    issue.reason,
                    format_door_side_details(issue.door_record),
                )
            )

    if result.failed_items:
        output.print_md("")
        output.print_md("## Failed Writes")
        for issue in sorted(result.failed_items, key=lambda value: get_issue_sort_key(value, preview.room_side_key)):
            if issue.target_value:
                output.print_md(
                    "- {0}: {1} Target value: `{2}` | {3}".format(
                        issue.door_record.door_label,
                        issue.reason,
                        issue.target_value,
                        format_door_side_details(issue.door_record),
                    )
                )
            else:
                output.print_md(
                    "- {0}: {1} | {2}".format(
                        issue.door_record.door_label,
                        issue.reason,
                        format_door_side_details(issue.door_record),
                    )
                )


def format_door_side_details(door_record):
    return "Facing: {0} | Opposite: {1}".format(
        format_room_state(door_record.facing_room, door_record.facing_issue),
        format_room_state(door_record.opposite_room, door_record.opposite_issue),
    )


def format_room_state(room_match, missing_reason):
    if room_match is None:
        return "None ({0})".format(missing_reason or "No room")

    room_parts = []
    if room_match.room_number:
        room_parts.append(room_match.room_number)
    if room_match.room_name:
        room_parts.append(room_match.room_name)

    room_text = " / ".join(room_parts)
    if not room_text:
        room_text = "Room {0}".format(room_match.room_id)

    source_parts = [room_match.source_label]
    if room_match.phase_name:
        source_parts.append(room_match.phase_name)

    return "{0} [{1}]".format(room_text, " | ".join(source_parts))


def append_skip_reason_summary(lines, skipped_items):
    if not skipped_items:
        return

    reason_counts = Counter()
    for issue in skipped_items:
        reason_counts[issue.reason] += 1

    lines.append("")
    lines.append("Skip reasons:")
    for reason, count in reason_counts.most_common():
        lines.append("  - {0}: {1}".format(count, reason))


def get_result_item_sort_key(planned_update):
    room_match = planned_update.room_match
    room_number = ""
    if room_match is not None:
        room_number = room_match.room_number
    return (engine.get_room_number_sort_key(room_number), planned_update.door_record.sort_key)


def get_issue_sort_key(issue_record, room_side_key):
    room_match = engine.get_room_match(issue_record.door_record, room_side_key)
    if room_match is None and issue_record.door_record.facing_room is not None:
        room_match = issue_record.door_record.facing_room
    if room_match is None and issue_record.door_record.opposite_room is not None:
        room_match = issue_record.door_record.opposite_room
    room_number = ""
    if room_match is not None:
        room_number = room_match.room_number
    return (engine.get_room_number_sort_key(room_number), issue_record.door_record.sort_key)


def format_suffix_summary(preview):
    if not preview.suffix_enabled:
        return "Disabled"

    style_label = engine.get_suffix_mode_label(preview.suffix_mode)
    separator_label = "'{0}'".format(preview.separator) if preview.separator else "(none)"
    return "{0}, separator: {1}".format(style_label, separator_label)


def format_yes_no(value):
    return "Yes" if value else "No"


if __name__ == "__main__":
    main()
