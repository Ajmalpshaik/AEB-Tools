# -*- coding: utf-8 -*-
"""
Tool Name    : Door Room Numbering Engine
Purpose      : Execute the core room lookup, suffixing, and parameter write logic for doors
Author       : Ajmal P.S.
Company      : AJ Tools
Version      : 1.0.0
Created      : 2026-04-21
Last Updated : 2026-04-21
Target       : Revit 2020-2027
Platform     : pyRevit / Python
Dependencies : Autodesk Revit API, pyRevit-compatible Python runtime
Input        : Revit document context, doors, rooms, command options
Output       : Door parameter update results, previews, and transaction status data
Notes        : Centralizes business logic so UI commands remain lightweight and maintainable
Changelog    : v1.0.0 - Added standardized metadata header
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from __future__ import absolute_import, division, print_function

from collections import Counter, defaultdict

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementCategoryFilter,
    ElementId,
    FamilyInstance,
    FilteredElementCollector,
    LocationCurve,
    LocationPoint,
    StorageType,
    Transaction,
    TransactionStatus,
)

try:
    text_type = unicode  # type: ignore[name-defined]
except NameError:
    text_type = str


SCOPE_ACTIVE_VIEW = "active_view"
SCOPE_CURRENT_SELECTION = "current_selection"
SCOPE_WHOLE_PROJECT = "whole_project"

SUFFIX_ALPHABETIC = "alphabetic"
SUFFIX_NUMERIC = "numeric"

DOOR_CATEGORY_FILTER = ElementCategoryFilter(BuiltInCategory.OST_Doors)


class ScopeState(object):
    def __init__(self, scope_key, scope_label, collection_note=None):
        self.scope_key = scope_key
        self.scope_label = scope_label
        self.collection_note = collection_note
        self.total_doors = 0
        self.resolved_door_count = 0
        self.room_group_count = 0
        self.grouped_door_count = 0
        self.string_parameter_instance_count = 0
        self.writable_string_parameter_instance_count = 0
        self.door_records = []
        self.parameter_choices = []


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
        self.door_id = safe_int(getattr(door.Id, "IntegerValue", None))
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
        self.is_grouped = element_is_grouped(door)


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
                 no_suffix_single, overwrite_existing):
        self.scope_state = scope_state
        self.parameter_choice = parameter_choice
        self.suffix_mode = suffix_mode
        self.separator = separator
        self.no_suffix_single = no_suffix_single
        self.overwrite_existing = overwrite_existing
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


def analyze_scope(doc, uidoc, active_view, scope_key):
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
            if is_door_instance(door):
                doors.append(door)

        if not selected_ids:
            collection_note = "No elements are selected. Pick door instances or switch to Whole Project."
        elif selected_ids and not doors:
            collection_note = "The current selection contains no host-document door instances."
    else:
        collector = None
        if scope_key == SCOPE_ACTIVE_VIEW:
            try:
                collector = FilteredElementCollector(doc, active_view.Id)
            except Exception:
                collection_note = "The active view could not be collected directly. Choose another scope if needed."
                collector = None

        if collector is None and scope_key != SCOPE_ACTIVE_VIEW:
            collector = FilteredElementCollector(doc)

        if collector is not None:
            doors = list(
                collector
                .OfCategory(BuiltInCategory.OST_Doors)
                .WhereElementIsNotElementType()
            )

        doors = [door for door in doors if is_door_instance(door)]

        if not doors and not collection_note:
            if scope_key == SCOPE_ACTIVE_VIEW:
                collection_note = "No visible host-document doors were found in the active view. Switch to Whole Project if the door exists elsewhere."
            elif scope_key == SCOPE_WHOLE_PROJECT:
                collection_note = "No host-document door instances were found in the project."

    doors = sorted(doors, key=lambda door: safe_int(getattr(door.Id, "IntegerValue", None)))
    phase_candidates = get_phase_candidates(doc, active_view)

    state = ScopeState(scope_key, get_scope_label(scope_key), collection_note)
    state.total_doors = len(doors)

    parameter_map = {}

    for door in doors:
        record = build_door_record(doc, door, phase_candidates)
        state.door_records.append(record)
        if record.is_grouped:
            state.grouped_door_count += 1

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

    valid_room_numbers = [
        record.room_number
        for record in state.door_records
        if not record.base_skip_reason
    ]
    state.resolved_door_count = len(valid_room_numbers)
    state.room_group_count = len(set(valid_room_numbers))
    state.parameter_choices = finalize_parameter_choices(parameter_map, state.total_doors)
    return state


def build_preview(scope_state, parameter_key, suffix_mode, separator,
                  no_suffix_single, overwrite_existing):
    parameter_choice = find_parameter_choice(scope_state, parameter_key)
    preview = PreviewResult(
        scope_state=scope_state,
        parameter_choice=parameter_choice,
        suffix_mode=suffix_mode,
        separator=separator or "",
        no_suffix_single=no_suffix_single,
        overwrite_existing=overwrite_existing,
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
        suffix = text_type(index + 1)
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


def build_door_record(doc, door, phase_candidates):
    record = DoorRecord(door, get_door_sort_key(door))
    room, room_source, phase_name = resolve_associated_room(door, phase_candidates)

    if room is None:
        record.base_skip_reason = "No associated room was found for this door."
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


def resolve_associated_room(door, phase_candidates):
    # Prefer the room the door swings into, then the general room, then the opposite side.
    accessors = (
        ("ToRoom", "ToRoom"),
        ("Room", "Room"),
        ("FromRoom", "FromRoom"),
    )

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


def get_phase_candidates(doc, active_view):
    phases = []
    seen_ids = set()

    active_phase = get_view_phase(doc, active_view)
    if active_phase is not None:
        active_phase_id = safe_int(getattr(active_phase.Id, "IntegerValue", None))
        phases.append(active_phase)
        seen_ids.add(active_phase_id)

    document_phases = list(doc.Phases)
    document_phases.reverse()
    for phase in document_phases:
        phase_id = safe_int(getattr(phase.Id, "IntegerValue", None))
        if phase_id in seen_ids:
            continue
        phases.append(phase)
        seen_ids.add(phase_id)

    return phases


def get_view_phase(doc, active_view):
    if active_view is None:
        return None

    try:
        phase_param = active_view.get_Parameter(BuiltInParameter.VIEW_PHASE)
    except Exception:
        phase_param = None

    if phase_param is None:
        return None

    try:
        phase_id = phase_param.AsElementId()
    except Exception:
        phase_id = None

    if is_invalid_element_id(phase_id):
        return None

    try:
        return doc.GetElement(phase_id)
    except Exception:
        return None


def get_room_by_accessor(door, accessor_name, phase):
    if phase is not None:
        accessor = getattr(door, "get_{0}".format(accessor_name), None)
        if accessor is not None:
            try:
                return accessor(phase)
            except Exception:
                pass
        return None

    try:
        return getattr(door, accessor_name)
    except Exception:
        return None


def get_door_sort_key(door):
    point = None
    try:
        location = door.Location
    except Exception:
        location = None

    if isinstance(location, LocationPoint):
        point = location.Point
    elif isinstance(location, LocationCurve):
        try:
            point = location.Curve.Evaluate(0.5, True)
        except Exception:
            point = None

    if point is None:
        try:
            bbox = door.get_BoundingBox(None)
        except Exception:
            bbox = None

        if bbox is not None:
            point = bbox.Min
            try:
                x_value = (bbox.Min.X + bbox.Max.X) / 2.0
                y_value = (bbox.Min.Y + bbox.Max.Y) / 2.0
            except Exception:
                x_value = 0.0
                y_value = 0.0
        else:
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
    for choice in scope_state.parameter_choices:
        if choice.key == parameter_key:
            return choice
    return None


def iterate_parameters(element):
    try:
        return list(element.Parameters)
    except Exception:
        return []


def find_parameter_by_key(element, parameter_key):
    for parameter in iterate_parameters(element):
        if get_parameter_key(parameter) == parameter_key:
            return parameter
    return None


def is_door_instance(element):
    if element is None or not isinstance(element, FamilyInstance):
        return False

    try:
        return DOOR_CATEGORY_FILTER.PassesFilter(element)
    except Exception:
        return False


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
    try:
        return not is_invalid_element_id(element.GroupId)
    except Exception:
        return False


def is_invalid_element_id(element_id):
    if element_id is None:
        return True

    try:
        return element_id == ElementId.InvalidElementId
    except Exception:
        return False


def is_valid_api_object(api_object):
    if api_object is None:
        return False

    try:
        return api_object.IsValidObject
    except Exception:
        return True


def normalize_text(value):
    text_value = safe_text(value)
    if not text_value:
        return ""

    text_value = text_value.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    while "  " in text_value:
        text_value = text_value.replace("  ", " ")
    return text_value.strip()


def safe_text(value):
    if value is None:
        return ""

    try:
        return text_type(value)
    except Exception:
        try:
            return str(value)
        except Exception:
            return ""


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def clean_exception_message(error):
    message = normalize_text(error)
    return message or "Unexpected Revit API error."
