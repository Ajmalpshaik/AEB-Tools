# -*- coding: utf-8 -*-
"""
Tool Name    : Auto Dimension
Purpose      : Unit conversion, view-frame math, geometry helpers, and API guards.
Author       : Ajmal P.S.
Company      : AJ Tools
Version      : 1.0.0
Created      : 2026-04-25
Last Updated : 2026-04-26
Target       : Revit 2020-2027
Platform     : pyRevit / IronPython
Dependencies : Autodesk Revit API
Input        : Revit API objects and XYZ geometry.
Output       : Read-only helper return values.
Notes        : No model mutations happen in this module except transaction helpers.
Changelog    : v1.0.1 - No behaviour changes; recompiled with consolidated boundary records.
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from __future__ import absolute_import, division, print_function

import math

from Autodesk.Revit.DB import (
    ElementId,
    Line,
    Transaction,
    TransactionStatus,
    XYZ,
)

import constants
import models


def mm_to_feet(value_mm):
    return float(value_mm) / constants.MM_PER_FOOT


def feet_to_mm(value_feet):
    return float(value_feet) * constants.MM_PER_FOOT


def offset_in_feet(offset_mm, ring_factor, view_frame):
    scale = 1
    if view_frame is not None and view_frame.scale > 0:
        scale = view_frame.scale
    return mm_to_feet(float(offset_mm) * float(ring_factor) * float(scale))


def safe_int_id(element_id):
    if element_id is None:
        return -1
    try:
        return int(element_id.IntegerValue)
    except Exception:
        try:
            return int(element_id.Value)
        except Exception:
            return -1


def is_invalid_id(element_id):
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
        return bool(api_object.IsValidObject)
    except Exception:
        return True


def clean_exception_message(error):
    try:
        text = str(error)
    except Exception:
        return "Unexpected Revit API error."
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = " ".join(text.split())
    return text or "Unexpected Revit API error."


def build_view_frame(view):
    if view is None:
        return None
    try:
        right = normalize_xyz(view.RightDirection)
        up = normalize_xyz(view.UpDirection)
        normal = normalize_xyz(view.ViewDirection)
        origin = view.Origin
        scale = view.Scale
    except Exception:
        return None
    if right is None or up is None or normal is None or origin is None:
        return None
    crop_box = build_crop_box(view, origin, right, up)
    return models.ViewFrame(view, origin, right, up, normal, scale, crop_box)


def build_crop_box(view, origin, right, up):
    try:
        if not view.CropBoxActive:
            return None
    except Exception:
        return None

    try:
        crop = view.CropBox
    except Exception:
        return None
    if crop is None:
        return None

    try:
        transform = crop.Transform
        min_pt = crop.Min
        max_pt = crop.Max
    except Exception:
        return None

    points = []
    for x_value in (min_pt.X, max_pt.X):
        for y_value in (min_pt.Y, max_pt.Y):
            for z_value in (min_pt.Z, max_pt.Z):
                point = XYZ(x_value, y_value, z_value)
                try:
                    point = transform.OfPoint(point)
                except Exception:
                    pass
                points.append(point)

    if not points:
        return None

    u_values = []
    v_values = []
    for point in points:
        delta = point - origin
        u_values.append(delta.DotProduct(right))
        v_values.append(delta.DotProduct(up))

    return models.ViewCropBox(
        min(u_values),
        max(u_values),
        min(v_values),
        max(v_values),
    )


def project_to_uv(point, view_frame):
    if point is None or view_frame is None:
        return 0.0, 0.0
    delta = point - view_frame.origin
    return delta.DotProduct(view_frame.right), delta.DotProduct(view_frame.up)


def uv_to_world(u_value, v_value, view_frame, fallback_z_point=None):
    normal_distance = 0.0
    if fallback_z_point is not None and view_frame.normal is not None:
        try:
            normal_distance = (
                fallback_z_point - view_frame.origin
            ).DotProduct(view_frame.normal)
        except Exception:
            normal_distance = 0.0
    return (view_frame.origin
            + view_frame.right.Multiply(float(u_value))
            + view_frame.up.Multiply(float(v_value))
            + view_frame.normal.Multiply(normal_distance))


def axis_point_to_world(axis, along_value, constant_value, view_frame, anchor_point=None):
    if axis == constants.AXIS_U:
        return uv_to_world(along_value, constant_value, view_frame, anchor_point)
    return uv_to_world(constant_value, along_value, view_frame, anchor_point)


def vector_view_uv(vector, view_frame):
    if vector is None or view_frame is None:
        return 0.0, 0.0
    return vector.DotProduct(view_frame.right), vector.DotProduct(view_frame.up)


def classify_direction(direction_uv):
    u_value, v_value = direction_uv
    length = math.sqrt(u_value * u_value + v_value * v_value)
    if length < 1e-9:
        return constants.DIRECTION_OBLIQUE
    if abs(v_value / length) <= constants.DIRECTION_BUCKET_TOLERANCE:
        return constants.DIRECTION_ALONG_U
    if abs(u_value / length) <= constants.DIRECTION_BUCKET_TOLERANCE:
        return constants.DIRECTION_ALONG_V
    return constants.DIRECTION_OBLIQUE


def perpendicular_axis(axis):
    if axis == constants.AXIS_U:
        return constants.AXIS_V
    return constants.AXIS_U


def make_axis_line(axis, start_value, end_value, constant_value, view_frame, anchor_point=None):
    p1 = axis_point_to_world(axis, start_value, constant_value, view_frame, anchor_point)
    p2 = axis_point_to_world(axis, end_value, constant_value, view_frame, anchor_point)
    if p1 is None or p2 is None:
        return None
    try:
        if p1.IsAlmostEqualTo(p2):
            return None
    except Exception:
        pass
    try:
        return Line.CreateBound(p1, p2)
    except Exception:
        return None


def get_element_bbox_uv(element, view, view_frame):
    if element is None or view is None or view_frame is None:
        return None
    try:
        bbox = element.get_BoundingBox(view)
    except Exception:
        bbox = None
    if bbox is None:
        try:
            bbox = element.get_BoundingBox(None)
        except Exception:
            bbox = None
    if bbox is None:
        return None

    try:
        min_pt = bbox.Min
        max_pt = bbox.Max
        transform = bbox.Transform
    except Exception:
        return None

    points = []
    for x_value in (min_pt.X, max_pt.X):
        for y_value in (min_pt.Y, max_pt.Y):
            for z_value in (min_pt.Z, max_pt.Z):
                point = XYZ(x_value, y_value, z_value)
                try:
                    point = transform.OfPoint(point)
                except Exception:
                    pass
                points.append(point)

    if not points:
        return None

    u_values = []
    v_values = []
    for point in points:
        u_value, v_value = project_to_uv(point, view_frame)
        u_values.append(u_value)
        v_values.append(v_value)
    return (min(u_values), max(u_values), min(v_values), max(v_values))


def crop_box_to_tuple(crop_box):
    if crop_box is None:
        return None
    return (crop_box.u_lo, crop_box.u_hi, crop_box.v_lo, crop_box.v_hi)


def uv_boxes_intersect(box_a, box_b, tolerance=None):
    if box_a is None or box_b is None:
        return True
    if tolerance is None:
        tolerance = constants.COINCIDENT_TOLERANCE_FT
    a_u_lo, a_u_hi, a_v_lo, a_v_hi = box_a
    b_u_lo, b_u_hi, b_v_lo, b_v_hi = box_b
    if a_u_hi < b_u_lo - tolerance:
        return False
    if a_u_lo > b_u_hi + tolerance:
        return False
    if a_v_hi < b_v_lo - tolerance:
        return False
    if a_v_lo > b_v_hi + tolerance:
        return False
    return True


def element_intersects_crop(element, view, view_frame):
    crop_tuple = crop_box_to_tuple(getattr(view_frame, "crop_box", None))
    if crop_tuple is None:
        return True
    element_box = get_element_bbox_uv(element, view, view_frame)
    if element_box is None:
        return False
    return uv_boxes_intersect(element_box, crop_tuple)


def line_inside_crop(axis, start_value, end_value, constant_value, view_frame):
    crop = getattr(view_frame, "crop_box", None)
    if crop is None:
        return True
    low_value = min(start_value, end_value)
    high_value = max(start_value, end_value)
    tolerance = constants.COINCIDENT_TOLERANCE_FT
    if axis == constants.AXIS_U:
        if constant_value < crop.v_lo - tolerance or constant_value > crop.v_hi + tolerance:
            return False
        return low_value >= crop.u_lo - tolerance and high_value <= crop.u_hi + tolerance
    if constant_value < crop.u_lo - tolerance or constant_value > crop.u_hi + tolerance:
        return False
    return low_value >= crop.v_lo - tolerance and high_value <= crop.v_hi + tolerance


def is_element_hidden_in_view(element, view):
    if element is None or view is None:
        return True
    try:
        if element.IsHidden(view):
            return True
    except Exception:
        pass
    try:
        category = element.Category
        if category is not None and view.GetCategoryHidden(category.Id):
            return True
    except Exception:
        pass
    return False


def is_element_visible_in_view(element, view, view_frame=None):
    if not is_valid_api_object(element):
        return False
    if is_element_hidden_in_view(element, view):
        return False
    if view_frame is not None and not element_intersects_crop(element, view, view_frame):
        return False
    return True


def reference_stable_key(doc, reference):
    if reference is None:
        return ""
    try:
        return reference.ConvertToStableRepresentation(doc)
    except Exception:
        try:
            return "ref:{0}".format(safe_int_id(reference.ElementId))
        except Exception:
            return str(reference)


def safe_transaction(doc, name):
    transaction = Transaction(doc, name)
    transaction.Start()
    return transaction


def commit_or_rollback(transaction, succeeded):
    if transaction is None:
        return False
    try:
        if succeeded:
            transaction.Commit()
            return transaction.GetStatus() == TransactionStatus.Committed
        transaction.RollBack()
        return False
    except Exception:
        try:
            transaction.RollBack()
        except Exception:
            pass
        return False


def stable_sort(items, key_function):
    return sorted(items, key=key_function)


def near_equal(value_a, value_b, tolerance=None):
    if tolerance is None:
        tolerance = constants.COINCIDENT_TOLERANCE_FT
    return abs(float(value_a) - float(value_b)) <= tolerance


def normalize_xyz(vector):
    if vector is None:
        return None
    try:
        if vector.IsZeroLength():
            return None
        return vector.Normalize()
    except Exception:
        try:
            length = math.sqrt(vector.X * vector.X + vector.Y * vector.Y + vector.Z * vector.Z)
            if length < 1e-9:
                return None
            return XYZ(vector.X / length, vector.Y / length, vector.Z / length)
        except Exception:
            return None
