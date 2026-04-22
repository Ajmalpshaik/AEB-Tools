# -*- coding: utf-8 -*-
"""
Tool Name    : Shared Revit Utility Helpers
Purpose      : Centralize common Revit API guards, text normalization, and door collection helpers
Author       : Ajmal P.S.
Company      : AJ Tools
Version      : 1.0.0
Created      : 2026-04-22
Last Updated : 2026-04-22
Target       : Revit 2020-2027
Platform     : pyRevit / Python
Dependencies : Autodesk Revit API, pyRevit-compatible Python runtime
Input        : Revit API objects, text values, and door collection context
Output       : Shared utility results reused by multiple live tools
Notes        : Keeps active tool engines lean and avoids duplicated low-level API guard logic
Changelog    : v1.0.0 - Added shared door collection, phase lookup, and text utility helpers
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from __future__ import absolute_import, division, print_function

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementCategoryFilter,
    ElementId,
    FamilyInstance,
    FilteredElementCollector,
)


try:
    text_type = unicode  # type: ignore[name-defined]
except NameError:
    text_type = str


DOOR_CATEGORY_FILTER = ElementCategoryFilter(BuiltInCategory.OST_Doors)


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


def normalize_text(value):
    text_value = safe_text(value)
    if not text_value:
        return ""
    text_value = text_value.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return " ".join(text_value.split())


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def clean_exception_message(error):
    message = normalize_text(error)
    return message or "Unexpected Revit API error."


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
        object_id = api_object.Id
    except Exception:
        return False

    if is_invalid_element_id(object_id):
        return False

    try:
        return api_object.IsValidObject
    except Exception:
        return True


def element_is_grouped(element):
    try:
        return not is_invalid_element_id(element.GroupId)
    except Exception:
        return False


def is_door_instance(element):
    if element is None or not isinstance(element, FamilyInstance):
        return False

    try:
        return DOOR_CATEGORY_FILTER.PassesFilter(element)
    except Exception:
        return False


def collect_door_instances(doc, active_view=None):
    if doc is None:
        return []

    collector = (
        FilteredElementCollector(doc, active_view.Id)
        if active_view is not None
        else FilteredElementCollector(doc)
    )
    return list(
        collector
        .OfClass(FamilyInstance)
        .WherePasses(DOOR_CATEGORY_FILTER)
        .WhereElementIsNotElementType()
    )


def get_view_phase(doc, active_view):
    if doc is None or active_view is None:
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


def get_phase_candidates(doc, active_view):
    if doc is None:
        return []

    phases = []
    seen_ids = set()

    active_phase = get_view_phase(doc, active_view)
    if is_valid_api_object(active_phase):
        active_phase_id = safe_int(getattr(active_phase.Id, "IntegerValue", None))
        phases.append(active_phase)
        seen_ids.add(active_phase_id)

    try:
        document_phases = list(doc.Phases)
    except Exception:
        document_phases = []

    document_phases.reverse()
    for phase in document_phases:
        phase_id = safe_int(getattr(phase.Id, "IntegerValue", None))
        if phase_id in seen_ids:
            continue
        phases.append(phase)
        seen_ids.add(phase_id)

    return phases


def get_room_by_accessor(door, accessor_name, phase):
    if door is None:
        return None

    if phase is not None:
        accessor = getattr(door, "get_{0}".format(accessor_name), None)
        if callable(accessor):
            try:
                return accessor(phase)
            except Exception:
                return None
        return None

    try:
        room = getattr(door, accessor_name)
    except Exception:
        room = None

    if is_valid_api_object(room):
        return room
    return None
