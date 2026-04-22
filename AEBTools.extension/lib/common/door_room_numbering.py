# -*- coding: utf-8 -*-
"""
Tool Name    : Door Room Numbering Engine
Purpose      : Execute the core room lookup, suffixing, and parameter write logic for doors
Author       : Ajmal P.S.
Company      : AJ Tools
Version      : 1.0.2
Created      : 2026-04-21
Last Updated : 2026-04-22
Target       : Revit 2020-2027
Platform     : pyRevit / Python
Dependencies : Autodesk Revit API, pyRevit-compatible Python runtime
Input        : Revit document context, doors, rooms, command options
Output       : Door parameter update results, previews, and transaction status data
Notes        : Centralizes business logic so UI commands remain lightweight and maintainable
Changelog    : v1.0.2 - Added room-side point lookup with a legacy Revit fallback mode
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from __future__ import absolute_import, division, print_function

from collections import Counter, defaultdict
from math import sqrt

from Autodesk.Revit.DB import (
    LocationCurve,
    LocationPoint,
    StorageType,
    Transaction,
    TransactionStatus,
    XYZ,
)

from common import revit_utils as utils


SCOPE_ACTIVE_VIEW = "active_view"
SCOPE_CURRENT_SELECTION = "current_selection"
SCOPE_WHOLE_PROJECT = "whole_project"

SUFFIX_ALPHABETIC = "alphabetic"
SUFFIX_NUMERIC = "numeric"

ROOM_SOURCE_TO = "to_room"
ROOM_SOURCE_FROM = "from_room"
ROOM_SOURCE_AUTO = "auto"

ROOM_PROBE_MIN_OFFSET_FEET = 0.75
ROOM_PROBE_WALL_CLEARANCE_FEET = 0.25
ROOM_PROBE_HEIGHTS_FEET = (3.0, 1.0, 0.1)


class ScopeState(object):
    def __init__(self, scope_key, scope_label, collection_note=None, room_source_mode=ROOM_SOURCE_TO):
        self.scope_key = scope_key
        self.scope_label = scope_label
        self.collection_note = collection_note
        self.room_source_mode = room_source_mode
        self.total_doors = 0
        self.resolved_door_count = 0
        self.room_group_count = 0
        self.grouped_door_count = 0
        self.string_parameter_instance_count = 0
        self.writable_string_parameter_instance_count = 0
        self.door_records = []
        self.parameter_choices = []
        self.parameter_choice_map = {}


class ParameterChoice(object):
    def __init__(self, key, name, kind_label, total_scope_doors):
        self.key = key
        self.name = name
        self.kind_label = kind_label
        self.total_scope_doors = total_scope_doors
        self.present_count = 0
        self.writable_count = 0
        self.display_name = name


class DoorParameterState(object):
    def __init__(self, key, name, is_writable, current_value):
        self.key = key
        self.name = name
        self.is_writable = is_writable
        self.current_value = current_value


class DoorRecord(object):
    def __init__(self, door, sort_key):
        self.door = door
        self.door_id = utils.safe_int(getattr(door.Id, "IntegerValue", None))
        self.door_label = describe_door(door)
        self.sort_key = sort_key
        self.parameter_states = {}
        self.room = None
        self.room_id = None
        self.room_number = ""
        self.room_name = ""
        self.room_source = ""
        self.room_phase_name = ""
        self.base_skip_reason = None
        self.is_grouped = utils.element_is_grouped(door)


class IssueRecord(object):
    def __init__(self, door_record, reason, target_value=None):
        self.door_record = door_record
        self.reason = reason
        self.target_value = target_value


class PlannedUpdate(object):
    def __init__(self, door_record, target_value, current_value):
        self.door_record = door_record
        self.target_value = target_value
        self.current_value = current_value


class PreviewResult(object):
    def __init__(self, scope_state, parameter_choice, suffix_mode, separator,
                 no_suffix_single, overwrite_existing, room_source_mode):
        self.scope_state = scope_state
        self.parameter_choice = parameter_choice
        self.suffix_mode = suffix_mode
        self.separator = separator
        self.no_suffix_single = no_suffix_single
        self.overwrite_existing = overwrite_existing
        self.room_source_mode = room_source_mode
        self.total_doors = scope_state.total_doors
        self.resolved_door_count = scope_state.resolved_door_count
        self.room_group_count = scope_state.room_group_count
        self.update_items = []
        self.skipped_items = []
        self.blocking_message = None


class ExecutionResult(object):
    def __init__(self, preview_result):
        self.preview_result = preview_result
        self.updated_items = []
        self.skipped_items = list(preview_result.skipped_items)
        self.failed_items = []


def get_scope_label(scope_key):
    if scope_key == SCOPE_ACTIVE_VIEW:
        return "Active View Only"
    if scope_key == SCOPE_CURRENT_SELECTION:
        return "Current Selection Only"
    return "Whole Project"


def get_room_source_label(room_source_mode):
    if room_source_mode == ROOM_SOURCE_FROM:
        return "Opposite Side (Point Lookup)"
    if room_source_mode == ROOM_SOURCE_AUTO:
        return "Legacy Auto (ToRoom -> Room -> FromRoom)"
    return "Facing Side (Point Lookup)"


def analyze_scope(doc, uidoc, active_view, scope_key, room_source_mode=ROOM_SOURCE_TO):
    collection_note = None
    doors = []

    if scope_key == SCOPE_CURRENT_SELECTION:
        selected_ids = []
        if uidoc is not None:
            try:
                selected_ids = list(uidoc.Selection.GetElementIds())
            except Exception:
                selected_ids = []

        for element_id in selected_ids:
            door = doc.GetElement(element_id)
            if utils.is_door_instance(door):
                doors.append(door)

        if not selected_ids:
            collection_note = "No elements are selected. Pick door instances or switch to Whole Project."
        elif selected_ids and not doors:
            collection_note = "The current selection contains no host-document door instances."
    else:
        if scope_key == SCOPE_ACTIVE_VIEW:
            if active_view is None:
                collection_note = "The active view is unavailable. Choose another scope if needed."
            else:
                try:
                    doors = utils.collect_door_instances(doc, active_view)
                except Exception:
                    doors = []
                    collection_note = "The active view could not be collected directly. Choose another scope if needed."
        else:
            try:
                doors = utils.collect_door_instances(doc)
            except Exception:
                collection_note = "Door collection failed for the selected scope. Try again or switch scope if needed."

        if not doors and not collection_note:
            if scope_key == SCOPE_ACTIVE_VIEW:
                collection_note = "No visible host-document doors were found in the active view. Switch to Whole Project if the door exists elsewhere."
            elif scope_key == SCOPE_WHOLE_PROJECT:
                collection_note = "No host-document door instances were found in the project."

    doors.sort(key=lambda door: utils.safe_int(getattr(door.Id, "IntegerValue", None)))
    phase_candidates = utils.get_phase_candidates(doc, active_view)

    state = ScopeState(
        scope_key,
        get_scope_label(scope_key),
        collection_note,
        room_source_mode=room_source_mode,
    )
    state.total_doors = len(doors)

    parameter_map = {}
    resolved_room_numbers = set()

    for door in doors:
        record = build_door_record(doc, door, phase_candidates, room_source_mode)
        state.door_records.append(record)
        if record.is_grouped:
            state.grouped_door_count += 1
        if not record.base_skip_reason:
            state.resolved_door_count += 1
            resolved_room_numbers.add(record.room_number)

        for parameter in iterate_parameters(door):
            if not is_string_parameter(parameter):
                continue

            state.string_parameter_instance_count += 1
            key = get_parameter_key(parameter)
            if key is None:
                continue

            name = get_parameter_name(parameter)
            parameter_state = DoorParameterState(
                key=key,
                name=name,
                is_writable=is_writable_string_parameter(parameter),
                current_value=safe_parameter_as_string(parameter),
            )
            record.parameter_states[key] = parameter_state

            choice = parameter_map.get(key)
            if choice is None:
                choice = ParameterChoice(
                    key=key,
                    name=name,
                    kind_label=get_parameter_kind_label(key),
                    total_scope_doors=state.total_doors,
                )
                parameter_map[key] = choice

            choice.present_count += 1
            if parameter_state.is_writable:
                state.writable_string_parameter_instance_count += 1
                choice.writable_count += 1

    state.room_group_count = len(resolved_room_numbers)
    state.parameter_choices = finalize_parameter_choices(parameter_map, state.total_doors)
    state.parameter_choice_map = dict((choice.key, choice) for choice in state.parameter_choices)
    return state


def build_preview(scope_state, parameter_key, suffix_mode, separator,
                  no_suffix_single, overwrite_existing, room_source_mode=None):
    selected_room_source_mode = room_source_mode or scope_state.room_source_mode
    parameter_choice = find_parameter_choice(scope_state, parameter_key)
    preview = PreviewResult(
        scope_state=scope_state,
        parameter_choice=parameter_choice,
        suffix_mode=suffix_mode,
        separator=separator or "",
        no_suffix_single=no_suffix_single,
        overwrite_existing=overwrite_existing,
        room_source_mode=selected_room_source_mode,
    )

    room_groups = defaultdict(list)
    for record in scope_state.door_records:
        if record.base_skip_reason:
            preview.skipped_items.append(IssueRecord(record, record.base_skip_reason))
            continue
        room_groups[record.room_number].append(record)

    if parameter_choice is None:
        if not scope_state.total_doors:
            preview.blocking_message = "No doors were found in the selected scope."
        elif not scope_state.parameter_choices:
            preview.blocking_message = "No writable text door parameters were found in this scope."
        else:
            preview.blocking_message = "Select a writable text parameter to continue."
        return preview

    if parameter_choice.writable_count == 0:
        preview.blocking_message = "The selected parameter is not writable for any door in this scope."
        return preview

    for room_number in sorted(room_groups.keys(), key=lambda value: value.lower()):
        grouped_records = sorted(room_groups[room_number], key=lambda item: item.sort_key)
        group_count = len(grouped_records)

        for index, record in enumerate(grouped_records):
            target_value = build_target_value(
                room_number=room_number,
                group_count=group_count,
                index=index,
                suffix_mode=suffix_mode,
                separator=preview.separator,
                no_suffix_single=no_suffix_single,
            )

            parameter_state = record.parameter_states.get(parameter_choice.key)
            if parameter_state is None:
                preview.skipped_items.append(
                    IssueRecord(record, "Selected parameter is missing or not text-compatible on this door.", target_value)
                )
                continue

            if not parameter_state.is_writable:
                preview.skipped_items.append(
                    IssueRecord(record, "Selected parameter is read-only on this door.", target_value)
                )
                continue

            current_value = normalize_text(parameter_state.current_value)
            if current_value == target_value:
                preview.skipped_items.append(
                    IssueRecord(record, "Parameter already matches the target value.", target_value)
                )
                continue

            if current_value and not overwrite_existing:
                preview.skipped_items.append(
                    IssueRecord(
                        record,
                        "Existing value '{0}' was preserved because overwrite is disabled.".format(current_value),
                        target_value,
                    )
                )
                continue

            preview.update_items.append(
                PlannedUpdate(record, target_value=target_value, current_value=current_value)
            )

    return preview


def execute_write_plan(doc, preview_result):
    result = ExecutionResult(preview_result)
    if not preview_result.update_items:
        return result

    attempted_successes = []
    transaction = Transaction(doc, "Room to Door")
    started = False
    committed = False

    try:
        started = transaction.Start() == TransactionStatus.Started
        if not started:
            raise Exception("The Revit transaction could not be started.")

        for planned_update in preview_result.update_items:
            record = planned_update.door_record
            door = record.door

            if not is_valid_api_object(door):
                result.failed_items.append(
                    IssueRecord(record, "Door element is no longer valid in the current document.", planned_update.target_value)
                )
                continue

            parameter = find_parameter_by_key(door, preview_result.parameter_choice.key)
            if parameter is None or not is_string_parameter(parameter):
                result.failed_items.append(
                    IssueRecord(record, "Selected parameter is no longer available as a text parameter.", planned_update.target_value)
                )
                continue

            if not is_writable_string_parameter(parameter):
                result.failed_items.append(
                    IssueRecord(record, "Selected parameter became read-only before writing.", planned_update.target_value)
                )
                continue

            current_value = normalize_text(safe_parameter_as_string(parameter))
            if current_value == planned_update.target_value:
                result.skipped_items.append(
                    IssueRecord(record, "Parameter already matches the target value.", planned_update.target_value)
                )
                continue

            if current_value and not preview_result.overwrite_existing:
                result.skipped_items.append(
                    IssueRecord(
                        record,
                        "Existing value '{0}' changed before writing and overwrite is disabled.".format(current_value),
                        planned_update.target_value,
                    )
                )
                continue

            try:
                changed = parameter.Set(planned_update.target_value)
                post_value = normalize_text(safe_parameter_as_string(parameter))
                if changed or post_value == planned_update.target_value:
                    attempted_successes.append(planned_update)
                else:
                    result.failed_items.append(
                        IssueRecord(record, "Revit rejected the parameter value.", planned_update.target_value)
                    )
            except Exception as write_error:
                result.failed_items.append(
                    IssueRecord(record, clean_exception_message(write_error), planned_update.target_value)
                )

        committed = transaction.Commit() == TransactionStatus.Committed
        if not committed:
            raise Exception("The Revit transaction did not commit successfully.")
    except Exception as transaction_error:
        if started and not committed:
            try:
                transaction.RollBack()
            except Exception:
                pass

        rollback_reason = "Transaction failed and was rolled back: {0}".format(
            clean_exception_message(transaction_error)
        )
        for planned_update in attempted_successes:
            result.failed_items.append(
                IssueRecord(planned_update.door_record, rollback_reason, planned_update.target_value)
            )
        attempted_successes = []

    result.updated_items.extend(attempted_successes)
    return result


def build_target_value(room_number, group_count, index, suffix_mode, separator, no_suffix_single):
    if group_count == 1 and no_suffix_single:
        return room_number

    if suffix_mode == SUFFIX_NUMERIC:
        suffix = str(index + 1)
    else:
        suffix = index_to_alphabetic(index)

    if separator:
        return "{0}{1}{2}".format(room_number, separator, suffix)
    return "{0}{1}".format(room_number, suffix)


def index_to_alphabetic(index):
    index = safe_int(index)
    if index < 0:
        index = 0

    letters = []
    value = index + 1
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        letters.append(chr(65 + remainder))
    letters.reverse()
    return "".join(letters)


def build_door_record(doc, door, phase_candidates, room_source_mode):
    record = DoorRecord(door, get_door_sort_key(door))
    room, room_source, phase_name = resolve_associated_room(door, phase_candidates, room_source_mode)

    if not is_valid_api_object(room):
        record.base_skip_reason = build_missing_room_message(room_source_mode)
        return record

    record.room = room
    record.room_id = safe_int(getattr(room.Id, "IntegerValue", None))
    record.room_source = room_source
    record.room_phase_name = phase_name
    record.room_name = safe_text(getattr(room, "Name", ""))

    room_number = normalize_text(getattr(room, "Number", ""))
    if not room_number:
        record.base_skip_reason = "Associated room has an empty Room Number."
        return record

    record.room_number = room_number
    return record


def build_missing_room_message(room_source_mode):
    if room_source_mode == ROOM_SOURCE_FROM:
        return "No room was found on the opposite side of this door."
    if room_source_mode == ROOM_SOURCE_AUTO:
        return "No associated room was found for this door."
    return "No room was found on the facing side of this door."


def get_room_accessors(room_source_mode):
    if room_source_mode == ROOM_SOURCE_FROM:
        return (
            ("FromRoom", "FromRoom"),
        )
    if room_source_mode == ROOM_SOURCE_AUTO:
        return (
            ("ToRoom", "ToRoom"),
            ("Room", "Room"),
            ("FromRoom", "FromRoom"),
        )
    return (
        ("ToRoom", "ToRoom"),
    )


def resolve_associated_room(door, phase_candidates, room_source_mode):
    if room_source_mode != ROOM_SOURCE_AUTO:
        return resolve_associated_room_by_points(
            door.Document,
            door,
            phase_candidates,
            use_facing_side=(room_source_mode == ROOM_SOURCE_TO),
        )

    return resolve_associated_room_legacy(door, phase_candidates)


def resolve_associated_room_legacy(door, phase_candidates):
    accessors = get_room_accessors(ROOM_SOURCE_AUTO)

    for phase in phase_candidates:
        for accessor_name, source_label in accessors:
            room = get_room_by_accessor(door, accessor_name, phase)
            if is_valid_api_object(room):
                return room, source_label, safe_text(getattr(phase, "Name", ""))

    for accessor_name, source_label in accessors:
        room = get_room_by_accessor(door, accessor_name, None)
        if is_valid_api_object(room):
            return room, source_label, ""

    return None, "", ""


def resolve_associated_room_by_points(doc, door, phase_candidates, use_facing_side):
    probe_sets = build_room_probe_sets(door)
    if not probe_sets:
        return None, "", ""

    source_label = "FacingSidePoint" if use_facing_side else "OppositeSidePoint"

    for phase in phase_candidates:
        for facing_point, opposite_point in probe_sets:
            point = facing_point if use_facing_side else opposite_point
            room = get_room_at_point(doc, point, phase)
            if is_valid_api_object(room):
                return room, source_label, safe_text(getattr(phase, "Name", ""))

    for facing_point, opposite_point in probe_sets:
        point = facing_point if use_facing_side else opposite_point
        room = get_room_at_point(doc, point, None)
        if is_valid_api_object(room):
            return room, source_label, ""

    return None, "", ""


def build_room_probe_sets(door):
    origin = get_door_origin_point(door)
    facing = normalize_xyz(get_xyz_property(door, "FacingOrientation"))
    if origin is None or facing is None:
        return []

    offset_distance = get_room_probe_offset_distance(door)
    probe_sets = []
    for height_offset in ROOM_PROBE_HEIGHTS_FEET:
        lifted_origin = XYZ(origin.X, origin.Y, origin.Z + float(height_offset))
        facing_point = XYZ(
            lifted_origin.X + (facing.X * offset_distance),
            lifted_origin.Y + (facing.Y * offset_distance),
            lifted_origin.Z + (facing.Z * offset_distance),
        )
        opposite_point = XYZ(
            lifted_origin.X - (facing.X * offset_distance),
            lifted_origin.Y - (facing.Y * offset_distance),
            lifted_origin.Z - (facing.Z * offset_distance),
        )
        probe_sets.append((facing_point, opposite_point))
    return probe_sets


def get_door_origin_point(door):
    try:
        location = door.Location
    except Exception:
        location = None

    if isinstance(location, LocationPoint):
        try:
            return location.Point
        except Exception:
            pass

    if isinstance(location, LocationCurve):
        try:
            return location.Curve.Evaluate(0.5, True)
        except Exception:
            pass

    try:
        bbox = door.get_BoundingBox(None)
    except Exception:
        bbox = None

    if bbox is not None:
        try:
            return XYZ(
                (bbox.Min.X + bbox.Max.X) / 2.0,
                (bbox.Min.Y + bbox.Max.Y) / 2.0,
                (bbox.Min.Z + bbox.Max.Z) / 2.0,
            )
        except Exception:
            return None

    return None


def get_room_probe_offset_distance(door):
    offset_distance = ROOM_PROBE_MIN_OFFSET_FEET

    try:
        host = door.Host
    except Exception:
        host = None

    host_width = safe_float(getattr(host, "Width", None), 0.0)
    if host_width > 0.0:
        offset_distance = max(
            ROOM_PROBE_MIN_OFFSET_FEET,
            (host_width / 2.0) + ROOM_PROBE_WALL_CLEARANCE_FEET,
        )
    return offset_distance


def get_room_at_point(doc, point, phase):
    if doc is None or point is None:
        return None

    try:
        if phase is not None:
            return doc.GetRoomAtPoint(point, phase)
        return doc.GetRoomAtPoint(point)
    except Exception:
        return None


def get_xyz_property(element, property_name):
    try:
        return getattr(element, property_name)
    except Exception:
        return None


def normalize_xyz(value):
    if value is None:
        return None

    try:
        length = value.GetLength()
    except Exception:
        try:
            length = sqrt((value.X * value.X) + (value.Y * value.Y) + (value.Z * value.Z))
        except Exception:
            length = 0.0

    if length <= 0.0:
        return None

    return XYZ(value.X / length, value.Y / length, value.Z / length)


def get_room_by_accessor(door, accessor_name, phase):
    return utils.get_room_by_accessor(door, accessor_name, phase)


def get_door_sort_key(door):
    point = get_door_origin_point(door)
    if point is None:
        x_value = 0.0
        y_value = 0.0
    else:
        x_value = point.X
        y_value = point.Y

    return (
        round(float(x_value), 6),
        round(float(y_value), 6),
        safe_int(getattr(door.Id, "IntegerValue", None)),
    )


def finalize_parameter_choices(parameter_map, total_scope_doors):
    choices = [
        choice
        for choice in parameter_map.values()
        if choice.writable_count > 0
    ]

    name_counter = Counter(choice.name.lower() for choice in choices)
    for choice in choices:
        display_name = choice.name
        if name_counter[choice.name.lower()] > 1:
            display_name = "{0} [{1} {2}]".format(
                choice.name,
                choice.kind_label,
                get_parameter_key_display_suffix(choice.key),
            )
        choice.display_name = "{0} ({1}/{2} writable)".format(
            display_name,
            choice.writable_count,
            total_scope_doors,
        )

    return sorted(choices, key=lambda item: item.display_name.lower())


def find_parameter_choice(scope_state, parameter_key):
    return scope_state.parameter_choice_map.get(parameter_key)


def iterate_parameters(element):
    try:
        return element.Parameters
    except Exception:
        return ()


def find_parameter_by_key(element, parameter_key):
    for parameter in iterate_parameters(element):
        if get_parameter_key(parameter) == parameter_key:
            return parameter
    return None


def is_door_instance(element):
    return utils.is_door_instance(element)


def get_parameter_key(parameter):
    if parameter is None:
        return None

    try:
        parameter_id = parameter.Id
        integer_value = getattr(parameter_id, "IntegerValue", None)
        if integer_value is not None:
            return "id:{0}".format(safe_int(integer_value))
    except Exception:
        pass

    try:
        parameter_guid = parameter.GUID
        if parameter_guid is not None:
            return "guid:{0}".format(normalize_text(parameter_guid))
    except Exception:
        pass

    name = get_parameter_name(parameter)
    if name:
        return "name:{0}".format(name.lower())
    return None


def get_parameter_name(parameter):
    try:
        definition = parameter.Definition
        if definition is not None:
            return normalize_text(definition.Name) or "Unnamed Parameter"
    except Exception:
        pass
    return "Unnamed Parameter"


def get_parameter_kind_label(parameter_key):
    key_text = safe_text(parameter_key)
    if key_text.startswith("id:-"):
        return "Built-in"
    if key_text.startswith("guid:"):
        return "Shared"
    return "Custom"


def get_parameter_key_display_suffix(parameter_key):
    key_text = safe_text(parameter_key)
    if ":" in key_text:
        return key_text.split(":", 1)[1]
    return key_text or "?"


def is_string_parameter(parameter):
    if parameter is None:
        return False
    try:
        return parameter.StorageType == StorageType.String
    except Exception:
        return False


def is_writable_string_parameter(parameter):
    if not is_string_parameter(parameter):
        return False
    try:
        return not parameter.IsReadOnly
    except Exception:
        return False


def safe_parameter_as_string(parameter):
    if parameter is None:
        return ""
    try:
        value = parameter.AsString()
    except Exception:
        value = None
    return normalize_text(value)


def describe_door(door):
    door_id = safe_int(getattr(door.Id, "IntegerValue", None))
    family_name = ""
    type_name = ""

    try:
        type_name = safe_text(door.Name)
    except Exception:
        type_name = ""

    try:
        family_name = safe_text(door.Symbol.Family.Name)
    except Exception:
        family_name = ""

    name_parts = [part for part in (family_name, type_name) if part]
    if name_parts:
        return "Door {0} ({1})".format(door_id, " : ".join(name_parts))
    return "Door {0}".format(door_id)


def element_is_grouped(element):
    return utils.element_is_grouped(element)


def is_invalid_element_id(element_id):
    return utils.is_invalid_element_id(element_id)


def is_valid_api_object(api_object):
    return utils.is_valid_api_object(api_object)


def normalize_text(value):
    return utils.normalize_text(value)


def safe_text(value):
    return utils.safe_text(value)


def safe_int(value, default=0):
    return utils.safe_int(value, default)


def safe_float(value, default=0.0):
    return utils.safe_float(value, default)


def clean_exception_message(error):
    return utils.clean_exception_message(error)
