# -*- coding: utf-8 -*-
"""
Tool Name    : Mirror Door Detection Engine
Purpose      : Collect host-document door instances and classify mirrored state for reporting and actions
Author       : Ajmal P.S.
Company      : AJ Tools
Version      : 1.2.4
Created      : 2026-04-22
Last Updated : 2026-04-22
Target       : Revit 2020-2027
Platform     : pyRevit / Python
Dependencies : Autodesk Revit API, pyRevit-compatible Python runtime
Input        : Revit document context, scope choice, and optional UI actions
Output       : Mirrored-door scan records, summary counts, and safe selection actions
Notes        : Uses the real FamilyInstance.Mirrored property and avoids guessed orientation logic
Changelog    : v1.2.4 - Switched room name/number reads to stable room built-in parameter fallbacks
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from __future__ import absolute_import, division, print_function

from Autodesk.Revit.DB import (
    BuiltInParameter,
    ElementId,
    RevitLinkInstance,
    Wall,
)
from System.Collections.Generic import List

from common import revit_utils as utils


SCOPE_CURRENT_SELECTION = "current_selection"
SCOPE_ACTIVE_VIEW = "active_view"
SCOPE_WHOLE_PROJECT = "whole_project"

HOST_ONLY_NOTE = "Linked model doors are not analyzed; only host-document door instances are processed."


class ScopeAnalysis(object):
    def __init__(self, scope_key, scope_label):
        self.scope_key = scope_key
        self.scope_label = scope_label
        self.collection_note = None
        self.host_only_note = HOST_ONLY_NOTE
        self.total_selected_elements = 0
        self.linked_selection_count = 0
        self.non_door_selection_count = 0
        self.invalid_selection_count = 0
        self.total_doors = 0
        self.checked_count = 0
        self.mirrored_count = 0
        self.non_mirrored_count = 0
        self.skipped_count = 0
        self.grouped_door_count = 0
        self.grouped_mirrored_count = 0
        self.records = []
        self.mirrored_records = []
        self.non_mirrored_records = []
        self.skipped_records = []


class DoorRecord(object):
    def __init__(self, door):
        self.door = door
        self.element_id = utils.safe_int(getattr(door.Id, "IntegerValue", None))
        self.family_name = ""
        self.type_name = ""
        self.level_name = ""
        self.host_label = ""
        self.mark = ""
        self.room_number = ""
        self.room_name = ""
        self.room_source = ""
        self.room_phase_name = ""
        self.is_mirrored = False
        self.is_grouped = False
        self.notes = []
        self.sort_key = ("~", "~", "~", self.element_id)


class SkippedDoorRecord(object):
    def __init__(self, element_id, reason):
        self.element_id = safe_int(element_id)
        self.reason = reason


def get_scope_label(scope_key):
    if scope_key == SCOPE_CURRENT_SELECTION:
        return "Selected Elements"
    if scope_key == SCOPE_ACTIVE_VIEW:
        return "Active View"
    return "Whole Project"


def inspect_scope(doc, uidoc, active_view, scope_key):
    analysis = ScopeAnalysis(scope_key, get_scope_label(scope_key))
    phase_candidates = utils.get_phase_candidates(doc, active_view)
    doors = []

    if scope_key == SCOPE_CURRENT_SELECTION:
        selected_ids = []
        if uidoc is not None:
            try:
                selected_ids = list(uidoc.Selection.GetElementIds())
            except Exception:
                selected_ids = []

        analysis.total_selected_elements = len(selected_ids)
        for element_id in selected_ids:
            element = doc.GetElement(element_id)
            if element is None:
                analysis.invalid_selection_count += 1
                continue
            if utils.is_door_instance(element):
                doors.append(element)
                continue
            if isinstance(element, RevitLinkInstance):
                analysis.linked_selection_count += 1
                continue
            analysis.non_door_selection_count += 1

        if not selected_ids:
            analysis.collection_note = "No elements are selected. Pick placed door instances or switch scope."
        elif not doors:
            analysis.collection_note = "The current selection contains no host-document door instances."
    else:
        if scope_key == SCOPE_ACTIVE_VIEW:
            if active_view is None:
                analysis.collection_note = "The active view is unavailable. Choose another scope if needed."
            else:
                try:
                    doors = utils.collect_door_instances(doc, active_view)
                except Exception:
                    doors = []
                    analysis.collection_note = "The active view cannot be scanned safely with view-based collection."
        else:
            try:
                doors = utils.collect_door_instances(doc)
            except Exception:
                analysis.collection_note = "Door collection failed for the selected scope. Try again or switch scope if needed."

        if not doors and not analysis.collection_note:
            if scope_key == SCOPE_ACTIVE_VIEW:
                analysis.collection_note = "No visible host-document doors were found in the active view."
            else:
                analysis.collection_note = "No host-document door instances were found in the project."

    analysis.total_doors = len(doors)

    for door in doors:
        if not is_valid_api_object(door):
            analysis.skipped_records.append(
                SkippedDoorRecord(
                    getattr(getattr(door, "Id", None), "IntegerValue", None),
                    "Door element is not a valid API object.",
                )
            )
            continue

        try:
            mirrored_state = bool(door.Mirrored)
        except Exception as mirrored_error:
            analysis.skipped_records.append(
                SkippedDoorRecord(
                    getattr(getattr(door, "Id", None), "IntegerValue", None),
                    "Mirrored property could not be read: {0}".format(clean_exception_message(mirrored_error)),
                )
            )
            continue

        record = build_door_record(doc, door, mirrored_state, phase_candidates)
        analysis.records.append(record)
        analysis.checked_count += 1

        if record.is_grouped:
            analysis.grouped_door_count += 1

        if record.is_mirrored:
            analysis.mirrored_records.append(record)
            analysis.mirrored_count += 1
            if record.is_grouped:
                analysis.grouped_mirrored_count += 1
        else:
            analysis.non_mirrored_records.append(record)
            analysis.non_mirrored_count += 1

    analysis.records = sorted(analysis.records, key=lambda item: item.sort_key)
    analysis.mirrored_records = sorted(analysis.mirrored_records, key=lambda item: item.sort_key)
    analysis.non_mirrored_records = sorted(analysis.non_mirrored_records, key=lambda item: item.sort_key)
    analysis.skipped_records = sorted(
        analysis.skipped_records,
        key=lambda item: (safe_int(item.element_id), normalize_text(item.reason).lower()),
    )
    analysis.skipped_count = len(analysis.skipped_records)
    return analysis


def build_door_record(doc, door, mirrored_state, phase_candidates):
    record = DoorRecord(door)
    record.is_mirrored = bool(mirrored_state)

    record.family_name = get_family_name(door)
    if not record.family_name:
        record.notes.append("Family name unavailable.")

    record.type_name = get_type_name(door)
    if not record.type_name:
        record.notes.append("Type name unavailable.")

    record.is_grouped = element_is_grouped(door)

    host = get_host_element(door)
    level_name = get_element_level_name(doc, door)
    if not level_name and host is not None:
        level_name = get_element_level_name(doc, host)
    record.level_name = level_name
    if not record.level_name:
        record.notes.append("Level unavailable.")

    host_label, host_note = get_host_label(host)
    record.host_label = host_label
    if host_note:
        record.notes.append(host_note)

    record.mark = get_mark_value(door)
    if not record.mark:
        record.notes.append("Mark unavailable.")

    room, room_source, room_phase_name = resolve_associated_room(door, phase_candidates)
    if is_valid_api_object(room):
        record.room_source = room_source
        record.room_phase_name = room_phase_name

        room_number = get_room_number_value(room)
        room_name = get_room_name_value(room)

        record.room_number = room_number
        record.room_name = room_name

        if not room_number:
            record.notes.append("Room number unavailable.")
        if not room_name:
            record.notes.append("Room name unavailable.")
    else:
        record.notes.append("Associated room unavailable.")

    record.notes = deduplicate_notes(record.notes)
    record.sort_key = (
        sort_text(record.level_name),
        sort_text(record.family_name),
        sort_text(record.type_name),
        record.element_id,
    )
    return record


def get_record_element_ids(records):
    result_ids = []
    for record in records:
        door = getattr(record, "door", None)
        if not is_valid_api_object(door):
            continue
        result_ids.append(door.Id)
    return sorted(result_ids, key=lambda element_id: utils.safe_int(getattr(element_id, "IntegerValue", None)))


def select_records(uidoc, records):
    if uidoc is None:
        return False, "Selection failed: no active Revit UI document."

    element_ids = get_record_element_ids(records)
    if not element_ids:
        return False, "Selection skipped: no matching door instances are available."

    dotnet_ids = to_element_id_list(element_ids)
    try:
        uidoc.Selection.SetElementIds(dotnet_ids)
        return True, "Selected {0} door(s).".format(len(element_ids))
    except Exception as selection_error:
        return False, "Selection failed: {0}".format(clean_exception_message(selection_error))


def to_element_id_list(element_ids):
    dotnet_ids = List[ElementId]()
    for element_id in element_ids:
        if is_invalid_element_id(element_id):
            continue
        dotnet_ids.Add(element_id)
    return dotnet_ids


def get_host_element(door):
    try:
        host = door.Host
    except Exception:
        host = None
    if is_valid_api_object(host):
        return host
    return None


def get_host_label(host):
    if host is None:
        return "", "Host unavailable."

    host_id = utils.safe_int(getattr(host.Id, "IntegerValue", None))
    host_name = normalize_text(getattr(host, "Name", ""))

    try:
        category_name = normalize_text(host.Category.Name)
    except Exception:
        category_name = ""

    if isinstance(host, Wall):
        if host_name:
            return "Wall {0} ({1})".format(host_id, host_name), None
        return "Wall {0}".format(host_id), None

    if category_name and host_name and host_name.lower() != category_name.lower():
        return "{0} {1} ({2})".format(category_name, host_id, host_name), None

    if category_name:
        return "{0} {1}".format(category_name, host_id), None

    if host_name:
        return "Host {0} ({1})".format(host_id, host_name), None

    return "Host {0}".format(host_id), None


def get_family_name(door):
    try:
        return normalize_text(door.Symbol.Family.Name)
    except Exception:
        return ""


def get_type_name(door):
    try:
        return normalize_text(door.Name)
    except Exception:
        return ""


def get_mark_value(element):
    return get_built_in_parameter_string(element, BuiltInParameter.ALL_MODEL_MARK)


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


def get_element_level_name(doc, element):
    if doc is None or element is None:
        return ""

    try:
        level_id = element.LevelId
    except Exception:
        level_id = None

    if is_invalid_element_id(level_id):
        return ""

    try:
        level = doc.GetElement(level_id)
    except Exception:
        level = None

    if not is_valid_api_object(level):
        return ""

    return normalize_text(getattr(level, "Name", ""))


def resolve_associated_room(door, phase_candidates):
    accessors = (
        ("ToRoom", "ToRoom"),
        ("Room", "Room"),
        ("FromRoom", "FromRoom"),
    )

    for phase in phase_candidates:
        for accessor_name, source_label in accessors:
            room = utils.get_room_by_accessor(door, accessor_name, phase)
            if is_valid_api_object(room):
                return room, source_label, normalize_text(getattr(phase, "Name", ""))

    for accessor_name, source_label in accessors:
        room = utils.get_room_by_accessor(door, accessor_name, None)
        if is_valid_api_object(room):
            return room, source_label, ""

    return None, "", ""


def is_door_instance(element):
    return utils.is_door_instance(element)


def element_is_grouped(element):
    return utils.element_is_grouped(element)


def is_invalid_element_id(element_id):
    return utils.is_invalid_element_id(element_id)


def is_valid_api_object(api_object):
    return utils.is_valid_api_object(api_object)


def sort_text(value):
    normalized = normalize_text(value)
    if not normalized:
        return "~"
    return normalized.lower()


def deduplicate_notes(notes):
    result = []
    seen = set()
    for note in notes:
        normalized = normalize_text(note)
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        result.append(normalized)
        seen.add(lowered)
    return result


def normalize_text(value):
    return utils.normalize_text(value)


def safe_text(value):
    return utils.safe_text(value)


def safe_int(value, default=0):
    return utils.safe_int(value, default)


def clean_exception_message(error):
    return utils.clean_exception_message(error)
