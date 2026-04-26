# -*- coding: utf-8 -*-
"""
Tool Name    : Auto Dimension
Purpose      : Plain data containers for automatic plan dimension creation.
Author       : Ajmal P.S.
Company      : AJ Tools
Version      : 1.0.0
Created      : 2026-04-25
Last Updated : 2026-04-26
Target       : Revit 2020-2027
Platform     : pyRevit / IronPython
Dependencies : Autodesk Revit API
Input        : Values produced by UI, collectors, and service logic.
Output       : Lightweight objects passed between modules.
Notes        : Keep this module dependency-light and side-effect free.
Changelog    : v1.0.1 - No structural changes; aligned with consolidated boundary records.
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from __future__ import absolute_import, division, print_function


class DimensionRequest(object):
    def __init__(self,
                 do_internal_rooms,
                 do_grids,
                 do_overall,
                 offset_mm,
                 dimension_type_id,
                 dry_run):
        self.do_internal_rooms = bool(do_internal_rooms)
        self.do_grids = bool(do_grids)
        self.do_overall = bool(do_overall)
        self.offset_mm = float(offset_mm)
        self.dimension_type_id = dimension_type_id
        self.dry_run = bool(dry_run)

    def has_any_task(self):
        return self.do_internal_rooms or self.do_grids or self.do_overall


class ViewFrame(object):
    """Active plan view coordinate frame.

    U follows view.RightDirection, V follows view.UpDirection, and N follows
    view.ViewDirection. All placement logic uses this frame instead of global X/Y.
    """

    def __init__(self, view, origin, right, up, normal, scale, crop_box=None):
        self.view = view
        self.origin = origin
        self.right = right
        self.up = up
        self.normal = normal
        self.scale = int(scale) if scale else 1
        self.crop_box = crop_box


class ViewCropBox(object):
    def __init__(self, u_lo, u_hi, v_lo, v_hi):
        self.u_lo = u_lo
        self.u_hi = u_hi
        self.v_lo = v_lo
        self.v_hi = v_hi


class WallExtent(object):
    def __init__(self,
                 wall,
                 u_lo,
                 u_hi,
                 v_lo,
                 v_hi,
                 direction_kind,
                 length):
        self.wall = wall
        self.u_lo = u_lo
        self.u_hi = u_hi
        self.v_lo = v_lo
        self.v_hi = v_hi
        self.direction_kind = direction_kind
        self.length = float(length or 0.0)


class ReferenceCandidate(object):
    def __init__(self, element, reference, axis, coordinate, stable_key):
        self.element = element
        self.reference = reference
        self.axis = axis
        self.coordinate = float(coordinate)
        self.stable_key = stable_key


class RoomBoundaryRecord(object):
    """Wall-backed room finish boundary segment in view UV space.

    segment_axis is the direction the boundary line runs.
    face_axis is the perpendicular axis measured by a dimension using this face.
    """

    def __init__(self,
                 room,
                 wall,
                 curve,
                 segment_axis,
                 face_axis,
                 along_min,
                 along_max,
                 face_coordinate,
                 length):
        self.room = room
        self.wall = wall
        self.curve = curve
        self.segment_axis = segment_axis
        self.face_axis = face_axis
        self.along_min = float(along_min)
        self.along_max = float(along_max)
        self.face_coordinate = float(face_coordinate)
        self.length = float(length or 0.0)


class DimensionSpec(object):
    def __init__(self,
                 label,
                 category,
                 element_id,
                 axis,
                 line_constant,
                 line,
                 candidates,
                 span_length):
        self.label = label
        self.category = category
        self.element_id = element_id
        self.axis = axis
        self.line_constant = float(line_constant)
        self.line = line
        self.candidates = list(candidates or [])
        self.span_length = float(span_length or 0.0)


class SkippedItem(object):
    def __init__(self, category, element_id, reason):
        self.category = category
        self.element_id = element_id
        self.reason = reason


class TaskOutcome(object):
    def __init__(self, label):
        self.label = label
        self.created_count = 0
        self.skipped_items = []
        self.notes = []

    def add_created(self, count=1):
        self.created_count += int(count)

    def add_skipped(self, category, element_id, reason):
        self.skipped_items.append(SkippedItem(category, element_id, reason))

    def add_note(self, note):
        if note:
            self.notes.append(note)


class ProcessReport(object):
    def __init__(self):
        self.outcomes = []
        self.success = False
        self.message = ""
        self.dry_run = False

    def add_outcome(self, outcome):
        if outcome is not None:
            self.outcomes.append(outcome)

    def total_created(self):
        return sum(outcome.created_count for outcome in self.outcomes)

    def total_skipped(self):
        return sum(len(outcome.skipped_items) for outcome in self.outcomes)

    def all_skipped(self):
        items = []
        for outcome in self.outcomes:
            items.extend(outcome.skipped_items)
        return items
