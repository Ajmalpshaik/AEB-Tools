# -*- coding: utf-8 -*-
"""
Tool Name    : Door Room Transfer Engine
Purpose      : Resolve door-side rooms deterministically and write stable room-number values to door parameters
Author       : Ajmal P.S.
Company      : AEB Tools
Version      : 1.0.1
Created      : 2026-04-25
Last Updated : 2026-04-25
Target       : Revit 2020-2027
Platform     : pyRevit / IronPython
Dependencies : Autodesk Revit API, pyRevit-compatible Python runtime
Input        : Revit document context, door scope, and user write settings
Output       : Preview data, write plans, and execution results for Room to Door
Notes        : Uses door location plus actual instance facing direction to resolve facing/opposite rooms predictably
Changelog    : v1.0.1 - Updated Room to Door to write room numbers with optional stable suffixing
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from __future__ import absolute_import, division, print_function

import re
from collections import Counter, defaultdict

from Autodesk.Revit.DB import (
    BuiltInParameter,
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

ROOM_SIDE_FACING = "facing_side"
ROOM_SIDE_OPPOSITE = "opposite_side"

SUFFIX_NUMERIC = "numeric"
SUFFIX_ALPHABETIC = "alphabetic"

ROOM_PROBE_MIN_OFFSET_FEET = 0.75
ROOM_PROBE_WALL_CLEARANCE_FEET = 0.25
ROOM_PROBE_HAND_NUDGE_FEET = 0.20
ROOM_PROBE_HEIGHTS_FEET = (3.0, 1.0, 0.1)
ROOM_SIDE_CLASSIFICATION_TOLERANCE_FEET = 0.10

ROOM_SOURCE_POINT_LOOKUP = "point_lookup"
ROOM_SOURCE_ACCESSOR_FALLBACK = "accessor_fallback"


class ScopeState(object):
    def __init__(self, scope_key, scope_label, collection_note=None):
        self.scope_key = scope_key
        self.scope_label = scope_label
        self.collection_note = collection_note
        self.total_doors = 0
        self.facing_room_count = 0
        self.opposite_room_count = 0
        self.grouped_door_count = 0
        self.string_parameter_instance_count = 0
        self.writable_string_parameter_instance_count = 0
        self.door_records = []
        self.parameter_choices = []
        self.parameter_choice_map = {}


class ParameterChoice(object):
    def __init__(self, key, name, kind_label):
        self.key = key
        self.name = name
        self.kind_label = kind_label
        self.present_count = 0
        self.writable_count = 0
        self.display_name = name


class DoorParameterState(object):
    def __init__(self, key, name, is_writable, current_value):
        self.key = key
        self.name = name
        self.is_writable = is_writable
        self.current_value = current_value


class DoorGeometry(object):
    def __init__(self):
        self.origin = None
        self.facing_vector = None
        self.hand_vector = None
        self.probe_distance = 0.0
        self.probe_sets = []
        self.issue = None


class RoomMatch(object):
    def __init__(self, room, phase_name, source_label, source_group):
        self.room = room
        self.room_id = safe_int(getattr(room.Id, "IntegerValue", None))
        self.room_number = get_room_number_value(room)
        self.room_name = get_room_name_value(room)
        self.phase_name = phase_name
        self.source_label = source_label
        self.source_group = source_group


class AccessorCandidate(object):
    def __init__(self, match, side_key=None):
        self.match = match
        self.side_key = side_key


class DoorRecord(object):
    def __init__(self, door):
        self.door = door
        self.door_id = utils.safe_int(getattr(door.Id, "IntegerValue", None))
        self.door_label = describe_door(door)
        self.sort_key = get_door_sort_key(door)
        self.parameter_states = {}
        self.geometry = None
        self.facing_room = None
        self.opposite_room = None
        self.facing_issue = None
        self.opposite_issue = None
        self.is_grouped = utils.element_is_grouped(door)


class IssueRecord(object):
    def __init__(self, door_record, reason, target_value=None):
        self.door_record = door_record
        self.reason = reason
        self.target_value = target_value


class PlannedUpdate(object):
    def __init__(self, door_record, room_match, target_value, current_value):
        self.door_record = door_record
        self.room_match = room_match
        self.target_value = target_value
        self.current_value = current_value


class PreviewResult(object):
    def __init__(self, scope_state, parameter_choice, room_side_key,
                 suffix_enabled, suffix_mode, separator, overwrite_existing):
        self.scope_state = scope_state
        self.parameter_choice = parameter_choice
        self.room_side_key = room_side_key
        self.suffix_enabled = suffix_enabled
        self.suffix_mode = suffix_mode
        self.separator = separator
        self.overwrite_existing = overwrite_existing
        self.total_doors = scope_state.total_doors
        self.selected_side_resolved_count = 0
        self.point_lookup_count = 0
        self.accessor_fallback_count = 0
        self.room_group_count = 0
        self.multi_door_room_count = 0
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
        return "Active View Doors"
    if scope_key == SCOPE_CURRENT_SELECTION:
        return "Selected Doors"
    return "Whole Project Doors"


def get_room_side_label(room_side_key):
    if room_side_key == ROOM_SIDE_OPPOSITE:
        return "Opposite Side Room"
    return "Facing Side Room"


def get_suffix_mode_label(suffix_mode):
    if suffix_mode == SUFFIX_ALPHABETIC:
        return "Alphabetic"
    return "Numeric"


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

    doors = deduplicate_doors(doors)
    doors.sort(key=get_door_sort_key)
    phase_candidates = utils.get_phase_candidates(doc, active_view)

    state = ScopeState(scope_key, get_scope_label(scope_key), collection_note)
    state.total_doors = len(doors)

    parameter_map = {}

    for door in doors:
        record = build_door_record(door, phase_candidates)
        state.door_records.append(record)

        if record.is_grouped:
            state.grouped_door_count += 1
        if record.facing_room is not None:
            state.facing_room_count += 1
        if record.opposite_room is not None:
            state.opposite_room_count += 1

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
                )
                parameter_map[key] = choice

            choice.present_count += 1
            if parameter_state.is_writable:
                state.writable_string_parameter_instance_count += 1
                choice.writable_count += 1

    state.parameter_choices = finalize_parameter_choices(parameter_map, state.total_doors)
    state.parameter_choice_map = dict((choice.key, choice) for choice in state.parameter_choices)
    return state


def build_preview(scope_state, parameter_key, room_side_key, suffix_enabled,
                  suffix_mode, separator, overwrite_existing):
    parameter_choice = find_parameter_choice(scope_state, parameter_key)
    preview = PreviewResult(
        scope_state=scope_state,
        parameter_choice=parameter_choice,
        room_side_key=room_side_key,
        suffix_enabled=bool(suffix_enabled),
        suffix_mode=suffix_mode,
        separator=sanitize_literal(separator),
        overwrite_existing=overwrite_existing,
    )
    summary = summarize_room_matches(scope_state.door_records, room_side_key)
    preview.selected_side_resolved_count = summary[0]
    preview.point_lookup_count = summary[1]
    preview.accessor_fallback_count = summary[2]

    room_groups = defaultdict(list)
    base_skipped_items = []
    for record in scope_state.door_records:
        room_match = get_room_match(record, room_side_key)
        if room_match is None:
            base_skipped_items.append(IssueRecord(record, get_room_issue(record, room_side_key)))
            continue

        room_number = room_match.room_number
        if not room_number:
            base_skipped_items.append(IssueRecord(record, "Associated room has an empty Room Number."))
            continue

        room_groups[room_number].append(record)

    preview.room_group_count = len(room_groups)
    preview.multi_door_room_count = len(
        [grouped_records for grouped_records in room_groups.values() if len(grouped_records) > 1]
    )

    preview.skipped_items.extend(base_skipped_items)

    if parameter_choice is None:
        if not scope_state.total_doors:
            preview.blocking_message = "No doors were found in the selected scope."
        elif not scope_state.parameter_choices:
            preview.blocking_message = "No writable text door parameters were found in this scope."
        else:
            preview.blocking_message = "Select a writable text parameter to continue."
        return preview

    for room_number in sorted(room_groups.keys(), key=get_room_number_sort_key):
        grouped_records = sorted(room_groups[room_number], key=lambda item: item.sort_key)
        group_count = len(grouped_records)

        for index, record in enumerate(grouped_records):
            room_match = get_room_match(record, room_side_key)
            target_value = build_target_value(
                room_number,
                group_count,
                index,
                preview.suffix_enabled,
                preview.suffix_mode,
                preview.separator,
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

            current_value = parameter_state.current_value
            if values_match(current_value, target_value):
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
                PlannedUpdate(
                    record,
                    room_match=room_match,
                    target_value=target_value,
                    current_value=current_value,
                )
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

            current_value = safe_parameter_as_string(parameter)
            if values_match(current_value, planned_update.target_value):
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
                post_value = safe_parameter_as_string(parameter)
                if changed or values_match(post_value, planned_update.target_value):
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
        handled_door_ids = set()
        for issue in result.skipped_items:
            handled_door_ids.add(issue.door_record.door_id)
        for issue in result.failed_items:
            handled_door_ids.add(issue.door_record.door_id)
        for planned_update in preview_result.update_items:
            if planned_update.door_record.door_id in handled_door_ids:
                continue
            result.failed_items.append(
                IssueRecord(planned_update.door_record, rollback_reason, planned_update.target_value)
            )
            handled_door_ids.add(planned_update.door_record.door_id)
        attempted_successes = []

    result.updated_items.extend(attempted_successes)
    return result


def summarize_room_matches(door_records, room_side_key):
    resolved_count = 0
    point_lookup_count = 0
    accessor_fallback_count = 0

    for record in door_records:
        room_match = get_room_match(record, room_side_key)
        if room_match is None:
            continue

        resolved_count += 1
        if room_match.source_group == ROOM_SOURCE_POINT_LOOKUP:
            point_lookup_count += 1
        elif room_match.source_group == ROOM_SOURCE_ACCESSOR_FALLBACK:
            accessor_fallback_count += 1

    return resolved_count, point_lookup_count, accessor_fallback_count


def build_target_value(room_number, group_count, index, suffix_enabled, suffix_mode, separator):
    separator_text = sanitize_literal(separator)
    if not room_number:
        return ""

    if (not suffix_enabled) or group_count <= 1:
        return room_number

    suffix_value = build_suffix_value(index, suffix_mode)
    if separator_text:
        return "{0}{1}{2}".format(room_number, separator_text, suffix_value)
    return "{0}{1}".format(room_number, suffix_value)


def build_door_record(door, phase_candidates):
    record = DoorRecord(door)
    record.geometry = collect_door_geometry(door)

    if record.geometry.issue:
        record.facing_issue = record.geometry.issue
        record.opposite_issue = record.geometry.issue
        return record

    # Primary lookup uses deterministic probe points on each side of the door.
    point_matches = resolve_point_room_matches(door.Document, record.geometry, phase_candidates)
    record.facing_room = point_matches.get(ROOM_SIDE_FACING)
    record.opposite_room = point_matches.get(ROOM_SIDE_OPPOSITE)

    accessor_candidates = []
    if record.facing_room is None or record.opposite_room is None:
        # Accessor fallback is only accepted when the side can still be resolved safely.
        accessor_candidates = collect_accessor_candidates(door, record.geometry, phase_candidates)

    if record.facing_room is None:
        record.facing_room = choose_accessor_fallback(
            ROOM_SIDE_FACING,
            accessor_candidates,
            record.facing_room,
            record.opposite_room,
        )

    if record.opposite_room is None:
        record.opposite_room = choose_accessor_fallback(
            ROOM_SIDE_OPPOSITE,
            accessor_candidates,
            record.facing_room,
            record.opposite_room,
        )

    record.facing_issue = build_missing_room_message(ROOM_SIDE_FACING) if record.facing_room is None else None
    record.opposite_issue = build_missing_room_message(ROOM_SIDE_OPPOSITE) if record.opposite_room is None else None
    return record


def collect_door_geometry(door):
    geometry = DoorGeometry()
    geometry.origin = get_door_origin_point(door)
    if geometry.origin is None:
        geometry.issue = "Door location point could not be resolved."
        return geometry

    facing_vector = normalize_horizontal_xyz(get_xyz_property(door, "FacingOrientation"))
    if facing_vector is None:
        facing_vector = normalize_xyz(get_xyz_property(door, "FacingOrientation"))
    if facing_vector is None:
        geometry.issue = "Door facing orientation could not be resolved."
        return geometry

    geometry.facing_vector = facing_vector
    geometry.hand_vector = normalize_horizontal_xyz(get_xyz_property(door, "HandOrientation"))
    if geometry.hand_vector is None:
        geometry.hand_vector = normalize_xyz(get_xyz_property(door, "HandOrientation"))

    geometry.probe_distance = get_room_probe_offset_distance(door)
    geometry.probe_sets = build_room_probe_sets(
        geometry.origin,
        geometry.facing_vector,
        geometry.hand_vector,
        geometry.probe_distance,
    )
    if not geometry.probe_sets:
        geometry.issue = "Door side probe points could not be created."
    return geometry


def resolve_point_room_matches(doc, geometry, phase_candidates):
    matches = {
        ROOM_SIDE_FACING: None,
        ROOM_SIDE_OPPOSITE: None,
    }

    for phase in build_phase_sequence(phase_candidates):
        phase_name = get_phase_name(phase)
        for facing_point, opposite_point in geometry.probe_sets:
            if matches[ROOM_SIDE_FACING] is None:
                facing_room = get_room_at_point(doc, facing_point, phase)
                if is_valid_api_object(facing_room):
                    matches[ROOM_SIDE_FACING] = create_room_match(
                        facing_room,
                        phase_name,
                        "Point Lookup",
                        ROOM_SOURCE_POINT_LOOKUP,
                    )

            if matches[ROOM_SIDE_OPPOSITE] is None:
                opposite_room = get_room_at_point(doc, opposite_point, phase)
                if is_valid_api_object(opposite_room):
                    matches[ROOM_SIDE_OPPOSITE] = create_room_match(
                        opposite_room,
                        phase_name,
                        "Point Lookup",
                        ROOM_SOURCE_POINT_LOOKUP,
                    )

            if matches[ROOM_SIDE_FACING] is not None and matches[ROOM_SIDE_OPPOSITE] is not None:
                return matches

    return matches


def collect_accessor_candidates(door, geometry, phase_candidates):
    candidates = []
    seen_keys = set()

    for phase in build_phase_sequence(phase_candidates):
        phase_name = get_phase_name(phase)
        for accessor_name in ("ToRoom", "FromRoom"):
            room = utils.get_room_by_accessor(door, accessor_name, phase)
            if not is_valid_api_object(room):
                continue

            room_id = safe_int(getattr(room.Id, "IntegerValue", None))
            candidate_key = (accessor_name, room_id)
            if candidate_key in seen_keys:
                continue
            seen_keys.add(candidate_key)

            candidates.append(
                AccessorCandidate(
                    match=create_room_match(
                        room,
                        phase_name,
                        accessor_name,
                        ROOM_SOURCE_ACCESSOR_FALLBACK,
                    ),
                    side_key=classify_room_side(geometry, room),
                )
            )

    return candidates


def choose_accessor_fallback(room_side_key, accessor_candidates, facing_room, opposite_room):
    matching_candidates = []
    for candidate in accessor_candidates:
        if candidate.side_key == room_side_key:
            matching_candidates.append(candidate)

    unique_match = get_unique_candidate_match(matching_candidates)
    if unique_match is not None:
        return unique_match

    # If one side is already known, the remaining unique accessor room can be used for the other side.
    other_side_match = opposite_room if room_side_key == ROOM_SIDE_FACING else facing_room
    if other_side_match is not None:
        return get_unique_candidate_match_excluding_room(accessor_candidates, other_side_match.room_id)

    return None


def get_unique_candidate_match(accessor_candidates):
    unique_by_room_id = {}
    ordered_room_ids = []

    for candidate in accessor_candidates:
        room_id = candidate.match.room_id
        if room_id not in unique_by_room_id:
            unique_by_room_id[room_id] = candidate.match
            ordered_room_ids.append(room_id)

    if len(ordered_room_ids) == 1:
        return unique_by_room_id[ordered_room_ids[0]]
    return None


def get_unique_candidate_match_excluding_room(accessor_candidates, excluded_room_id):
    filtered_candidates = []
    for candidate in accessor_candidates:
        if candidate.match.room_id == excluded_room_id:
            continue
        filtered_candidates.append(candidate)
    return get_unique_candidate_match(filtered_candidates)


def classify_room_side(geometry, room):
    if geometry is None or geometry.origin is None or geometry.facing_vector is None or room is None:
        return None

    room_point = get_room_location_point(room)
    if room_point is None:
        return None

    door_x = safe_float(getattr(geometry.origin, "X", None), 0.0)
    door_y = safe_float(getattr(geometry.origin, "Y", None), 0.0)
    room_x = safe_float(getattr(room_point, "X", None), 0.0)
    room_y = safe_float(getattr(room_point, "Y", None), 0.0)
    facing_x = safe_float(getattr(geometry.facing_vector, "X", None), 0.0)
    facing_y = safe_float(getattr(geometry.facing_vector, "Y", None), 0.0)

    dot_product = ((room_x - door_x) * facing_x) + ((room_y - door_y) * facing_y)
    if dot_product > ROOM_SIDE_CLASSIFICATION_TOLERANCE_FEET:
        return ROOM_SIDE_FACING
    if dot_product < (-ROOM_SIDE_CLASSIFICATION_TOLERANCE_FEET):
        return ROOM_SIDE_OPPOSITE
    return None


def build_phase_sequence(phase_candidates):
    result = []
    for phase in phase_candidates:
        result.append(phase)
    result.append(None)
    return result


def create_room_match(room, phase_name, source_label, source_group):
    return RoomMatch(room, phase_name, source_label, source_group)


def get_room_match(record, room_side_key):
    if room_side_key == ROOM_SIDE_OPPOSITE:
        return record.opposite_room
    return record.facing_room


def get_room_issue(record, room_side_key):
    if room_side_key == ROOM_SIDE_OPPOSITE:
        return record.opposite_issue or build_missing_room_message(ROOM_SIDE_OPPOSITE)
    return record.facing_issue or build_missing_room_message(ROOM_SIDE_FACING)


def build_missing_room_message(room_side_key):
    if room_side_key == ROOM_SIDE_OPPOSITE:
        return "No room was found on the opposite side of this door."
    return "No room was found on the facing side of this door."


def get_door_origin_point(door):
    try:
        location = door.Location
    except Exception:
        location = None

    if isinstance(location, LocationPoint):
        try:
            return location.Point
        except Exception:
            return None

    if isinstance(location, LocationCurve):
        try:
            return location.Curve.Evaluate(0.5, True)
        except Exception:
            return None

    return None


def build_room_probe_sets(origin, facing_vector, hand_vector, offset_distance):
    if origin is None or facing_vector is None or offset_distance <= 0.0:
        return []

    probe_sets = []
    hand_offsets = (0.0,)
    if hand_vector is not None:
        hand_offsets = (
            0.0,
            ROOM_PROBE_HAND_NUDGE_FEET,
            -ROOM_PROBE_HAND_NUDGE_FEET,
        )

    # FacingOrientation and HandOrientation are already transformed by Revit,
    # so mirrored/flipped instances probe the correct physical side.
    for height_offset in ROOM_PROBE_HEIGHTS_FEET:
        z_value = safe_float(getattr(origin, "Z", None), 0.0) + float(height_offset)
        base_x = safe_float(getattr(origin, "X", None), 0.0)
        base_y = safe_float(getattr(origin, "Y", None), 0.0)
        facing_x = safe_float(getattr(facing_vector, "X", None), 0.0)
        facing_y = safe_float(getattr(facing_vector, "Y", None), 0.0)
        facing_z = safe_float(getattr(facing_vector, "Z", None), 0.0)
        hand_x = safe_float(getattr(hand_vector, "X", None), 0.0)
        hand_y = safe_float(getattr(hand_vector, "Y", None), 0.0)
        hand_z = safe_float(getattr(hand_vector, "Z", None), 0.0)

        for hand_offset in hand_offsets:
            lateral_x = hand_x * hand_offset
            lateral_y = hand_y * hand_offset
            lateral_z = hand_z * hand_offset

            facing_point = XYZ(
                base_x + (facing_x * offset_distance) + lateral_x,
                base_y + (facing_y * offset_distance) + lateral_y,
                z_value + (facing_z * offset_distance) + lateral_z,
            )
            opposite_point = XYZ(
                base_x - (facing_x * offset_distance) + lateral_x,
                base_y - (facing_y * offset_distance) + lateral_y,
                z_value - (facing_z * offset_distance) + lateral_z,
            )
            probe_sets.append((facing_point, opposite_point))
    return probe_sets


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


def deduplicate_doors(doors):
    result = []
    seen_ids = set()

    for door in doors:
        door_id = safe_int(getattr(getattr(door, "Id", None), "IntegerValue", None), -1)
        if door_id in seen_ids:
            continue
        result.append(door)
        seen_ids.add(door_id)

    return result


def get_room_at_point(doc, point, phase):
    if doc is None or point is None:
        return None

    try:
        if phase is not None:
            return doc.GetRoomAtPoint(point, phase)
        return doc.GetRoomAtPoint(point)
    except Exception:
        return None


def get_room_location_point(room):
    if room is None:
        return None

    try:
        location = room.Location
    except Exception:
        location = None

    if isinstance(location, LocationPoint):
        try:
            return location.Point
        except Exception:
            return None

    try:
        return location.Point
    except Exception:
        return None


def get_phase_name(phase):
    if phase is None:
        return ""
    return normalize_text(getattr(phase, "Name", ""))


def get_xyz_property(element, property_name):
    try:
        return getattr(element, property_name)
    except Exception:
        return None


def normalize_xyz(value):
    if value is None:
        return None

    x_value = safe_float(getattr(value, "X", None), 0.0)
    y_value = safe_float(getattr(value, "Y", None), 0.0)
    z_value = safe_float(getattr(value, "Z", None), 0.0)
    length = ((x_value * x_value) + (y_value * y_value) + (z_value * z_value)) ** 0.5
    if length <= 0.0:
        return None

    return XYZ(x_value / length, y_value / length, z_value / length)


def normalize_horizontal_xyz(value):
    if value is None:
        return None

    x_value = safe_float(getattr(value, "X", None), 0.0)
    y_value = safe_float(getattr(value, "Y", None), 0.0)
    length = ((x_value * x_value) + (y_value * y_value)) ** 0.5
    if length <= 0.0:
        return None

    return XYZ(x_value / length, y_value / length, 0.0)


def get_door_sort_key(door):
    origin = get_door_origin_point(door)
    if origin is None:
        return (0.0, 0.0, 0.0, safe_int(getattr(door.Id, "IntegerValue", None)))

    return (
        round(safe_float(getattr(origin, "X", None), 0.0), 6),
        round(safe_float(getattr(origin, "Y", None), 0.0), 6),
        round(safe_float(getattr(origin, "Z", None), 0.0), 6),
        safe_int(getattr(door.Id, "IntegerValue", None)),
    )


def build_suffix_value(index, suffix_mode):
    if suffix_mode == SUFFIX_ALPHABETIC:
        return index_to_alphabetic(index)
    return str(index + 1)


def index_to_alphabetic(index):
    safe_index = safe_int(index, 0)
    if safe_index < 0:
        safe_index = 0

    letters = []
    value = safe_index + 1
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        letters.append(chr(65 + remainder))
    letters.reverse()
    return "".join(letters)


def get_room_number_sort_key(room_number):
    normalized_value = normalize_text(room_number)
    if not normalized_value:
        return ((1, ""),)

    tokens = []
    for token in re.split(r"(\d+)", normalized_value):
        if not token:
            continue
        if token.isdigit():
            tokens.append((0, safe_int(token)))
        else:
            tokens.append((1, token.lower()))
    return tuple(tokens)


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


def values_match(left_value, right_value):
    return normalize_text(left_value) == normalize_text(right_value)


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


def get_room_number_value(room):
    room_number = get_built_in_parameter_string(room, BuiltInParameter.ROOM_NUMBER)
    if room_number:
        return room_number

    try:
        room_number = getattr(room, "Number", "")
    except Exception:
        room_number = ""
    return normalize_text(room_number)


def get_room_name_value(room):
    room_name = get_built_in_parameter_string(room, BuiltInParameter.ROOM_NAME)
    if room_name:
        return room_name

    try:
        room_name = getattr(room, "Name", "")
    except Exception:
        room_name = ""
    return normalize_text(room_name)


def get_built_in_parameter_string(element, built_in_parameter):
    if element is None:
        return ""

    try:
        parameter = element.get_Parameter(built_in_parameter)
    except Exception:
        parameter = None

    if parameter is None:
        return ""

    try:
        value = parameter.AsString()
    except Exception:
        value = None
    return normalize_text(value)


def sanitize_literal(value):
    text_value = safe_text(value)
    return text_value.replace("\r", " ").replace("\n", " ").replace("\t", " ")


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
