# -*- coding: utf-8 -*-
"""
Tool Name    : Auto Dimension
Purpose      : Read-only collection and classification for automatic plan dimensions.
Author       : Ajmal P.S.
Company      : AJ Tools
Version      : 1.0.0
Created      : 2026-04-25
Last Updated : 2026-04-26
Target       : Revit 2020-2027
Platform     : pyRevit / IronPython
Dependencies : Autodesk Revit API
Input        : Active document, active plan view, and ViewFrame.
Output       : Visible rooms, grids, walls, room boundaries, and face references.
Notes        : This module never opens a transaction.
Changelog    : v1.0.1 - Consolidate split room boundary segments per wall face.
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from __future__ import absolute_import, division, print_function

from Autodesk.Revit.DB import (
    BuiltInCategory,
    DimensionStyleType,
    DimensionType,
    FilteredElementCollector,
    GeometryInstance,
    Grid,
    Line,
    LocationCurve,
    Options,
    PlanarFace,
    Solid,
    SpatialElementBoundaryLocation,
    SpatialElementBoundaryOptions,
    UV,
    Wall,
)

import constants
import models
import utils


def collect_walls_in_view(doc, view, view_frame):
    walls = (
        FilteredElementCollector(doc, view.Id)
        .OfClass(Wall)
        .WhereElementIsNotElementType()
    )
    return _collect_visible_elements(walls, view, view_frame)


def collect_grids_in_view(doc, view, view_frame):
    grids = (
        FilteredElementCollector(doc, view.Id)
        .OfClass(Grid)
        .WhereElementIsNotElementType()
    )
    return _collect_visible_elements(grids, view, view_frame)


def collect_rooms_in_view(doc, view, view_frame):
    rooms = (
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Rooms)
        .WhereElementIsNotElementType()
    )
    valid_rooms = []
    for room in rooms:
        if not utils.is_valid_api_object(room):
            continue
        try:
            if room.Area <= 0:
                continue
        except Exception:
            pass
        if not _room_matches_view_level(room, view):
            continue
        if not _room_intersects_view_crop(room, view, view_frame):
            continue
        valid_rooms.append(room)
    return utils.stable_sort(valid_rooms, lambda room: utils.safe_int_id(room.Id))


def collect_linear_dimension_types(doc):
    dim_types = FilteredElementCollector(doc).OfClass(DimensionType)
    linear_types = []
    for dim_type in dim_types:
        try:
            if dim_type.StyleType == DimensionStyleType.Linear:
                linear_types.append(dim_type)
        except Exception:
            continue
    return utils.stable_sort(linear_types, _dimension_type_sort_key)


def collect_room_boundary_records(doc, room, view_frame):
    records = []
    if room is None or view_frame is None:
        return records

    options = SpatialElementBoundaryOptions()
    try:
        options.SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Finish
    except Exception:
        pass

    try:
        boundary_loops = room.GetBoundarySegments(options)
    except Exception:
        boundary_loops = None
    if not boundary_loops:
        return records

    for boundary_loop in boundary_loops:
        for segment in boundary_loop:
            record = _boundary_record_from_segment(doc, room, segment, view_frame)
            if record is not None:
                records.append(record)

    records = consolidate_boundary_records(records)
    return utils.stable_sort(
        records,
        lambda item: (
            round(item.face_coordinate, 6),
            round(item.along_min, 6),
            utils.safe_int_id(item.wall.Id),
        ),
    )


def consolidate_boundary_records(records):
    """Merge records that point to the same wall face.

    An outside-side intersecting wall, T-junction, or split wall makes Revit
    return several adjacent boundary segments for what is logically one
    inside wall face. Without this merge, the dimension-line cross test in
    service.py can fall in the gap between split segments and skip a valid
    room side.
    """
    if not records:
        return records

    bucket_size_ft = utils.mm_to_feet(constants.FACE_COORDINATE_GROUP_MM)
    if bucket_size_ft <= 0.0:
        bucket_size_ft = utils.mm_to_feet(1.0)

    groups = {}
    order = []
    for record in records:
        wall_id = utils.safe_int_id(record.wall.Id)
        coord_key = int(round(record.face_coordinate / bucket_size_ft))
        key = (
            wall_id,
            record.face_axis,
            record.segment_axis,
            coord_key,
        )
        existing = groups.get(key)
        if existing is None:
            groups[key] = record
            order.append(key)
            continue

        existing.along_min = min(existing.along_min, record.along_min)
        existing.along_max = max(existing.along_max, record.along_max)
        existing.length = max(
            existing.length,
            existing.along_max - existing.along_min,
        )

    return [groups[key] for key in order]


def compute_wall_extent(wall, view_frame):
    curve = get_wall_location_curve(wall)
    if curve is None:
        return None
    try:
        start = curve.GetEndPoint(0)
        end = curve.GetEndPoint(1)
    except Exception:
        return None

    bbox_uv = utils.get_element_bbox_uv(wall, view_frame.view, view_frame)
    if bbox_uv is None:
        start_u, start_v = utils.project_to_uv(start, view_frame)
        end_u, end_v = utils.project_to_uv(end, view_frame)
        bbox_uv = (
            min(start_u, end_u),
            max(start_u, end_u),
            min(start_v, end_v),
            max(start_v, end_v),
        )

    direction_kind = utils.classify_direction(
        utils.vector_view_uv(end - start, view_frame)
    )
    try:
        length = curve.Length
    except Exception:
        length = 0.0

    return models.WallExtent(
        wall,
        bbox_uv[0],
        bbox_uv[1],
        bbox_uv[2],
        bbox_uv[3],
        direction_kind,
        length,
    )


def compute_building_uv_box(wall_extents):
    if not wall_extents:
        return None
    u_lo = wall_extents[0].u_lo
    u_hi = wall_extents[0].u_hi
    v_lo = wall_extents[0].v_lo
    v_hi = wall_extents[0].v_hi
    for extent in wall_extents[1:]:
        u_lo = min(u_lo, extent.u_lo)
        u_hi = max(u_hi, extent.u_hi)
        v_lo = min(v_lo, extent.v_lo)
        v_hi = max(v_hi, extent.v_hi)
    return (u_lo, u_hi, v_lo, v_hi)


def compute_grid_uv_box(grids, view_frame):
    points = []
    for grid in grids:
        curve = get_grid_line(grid)
        if curve is None:
            continue
        try:
            points.append(utils.project_to_uv(curve.GetEndPoint(0), view_frame))
            points.append(utils.project_to_uv(curve.GetEndPoint(1), view_frame))
        except Exception:
            continue
    if not points:
        return None
    u_values = [item[0] for item in points]
    v_values = [item[1] for item in points]
    return (min(u_values), max(u_values), min(v_values), max(v_values))


def collect_wall_face_candidates(doc, wall, view, view_frame):
    candidates = []
    options = Options()
    options.View = view
    options.ComputeReferences = True
    options.IncludeNonVisibleObjects = False
    try:
        geometry_element = wall.get_Geometry(options)
    except Exception:
        geometry_element = None
    if geometry_element is None:
        return candidates

    seen_keys = set()
    for geometry_object in geometry_element:
        _append_face_candidates_from_geometry(
            doc,
            wall,
            geometry_object,
            view_frame,
            candidates,
            seen_keys,
        )
    return utils.stable_sort(
        candidates,
        lambda item: (item.axis, round(item.coordinate, 6), item.stable_key),
    )


def get_wall_location_curve(wall):
    if wall is None:
        return None
    try:
        location = wall.Location
    except Exception:
        return None
    if isinstance(location, LocationCurve):
        return location.Curve
    return None


def get_grid_line(grid):
    try:
        curve = grid.Curve
    except Exception:
        return None
    if isinstance(curve, Line):
        return curve
    return None


def _collect_visible_elements(element_iterable, view, view_frame):
    elements = []
    for element in element_iterable:
        if utils.is_element_visible_in_view(element, view, view_frame):
            elements.append(element)
    return utils.stable_sort(elements, lambda element: utils.safe_int_id(element.Id))


def _room_matches_view_level(room, view):
    try:
        level = view.GenLevel
    except Exception:
        level = None
    if level is None:
        return True
    try:
        return utils.safe_int_id(room.LevelId) == utils.safe_int_id(level.Id)
    except Exception:
        return True


def _room_intersects_view_crop(room, view, view_frame):
    if view_frame is None or getattr(view_frame, "crop_box", None) is None:
        return True
    room_box = utils.get_element_bbox_uv(room, view, view_frame)
    if room_box is None:
        return True
    return utils.uv_boxes_intersect(room_box, utils.crop_box_to_tuple(view_frame.crop_box))


def _dimension_type_sort_key(dim_type):
    try:
        return dim_type.Name or ""
    except Exception:
        return ""


def _boundary_record_from_segment(doc, room, segment, view_frame):
    wall = _wall_from_boundary_segment(doc, segment)
    if wall is None:
        return None
    try:
        curve = segment.GetCurve()
    except Exception:
        return None
    if not isinstance(curve, Line):
        return None

    try:
        start = curve.GetEndPoint(0)
        end = curve.GetEndPoint(1)
    except Exception:
        return None

    start_u, start_v = utils.project_to_uv(start, view_frame)
    end_u, end_v = utils.project_to_uv(end, view_frame)
    direction_kind = utils.classify_direction(
        utils.vector_view_uv(end - start, view_frame)
    )

    if direction_kind == constants.DIRECTION_ALONG_U:
        segment_axis = constants.AXIS_U
        face_axis = constants.AXIS_V
        along_min = min(start_u, end_u)
        along_max = max(start_u, end_u)
        face_coordinate = 0.5 * (start_v + end_v)
    elif direction_kind == constants.DIRECTION_ALONG_V:
        segment_axis = constants.AXIS_V
        face_axis = constants.AXIS_U
        along_min = min(start_v, end_v)
        along_max = max(start_v, end_v)
        face_coordinate = 0.5 * (start_u + end_u)
    else:
        return None

    try:
        length = curve.Length
    except Exception:
        length = abs(along_max - along_min)

    return models.RoomBoundaryRecord(
        room,
        wall,
        curve,
        segment_axis,
        face_axis,
        along_min,
        along_max,
        face_coordinate,
        length,
    )


def _wall_from_boundary_segment(doc, segment):
    try:
        element_id = segment.ElementId
    except Exception:
        return None
    if utils.is_invalid_id(element_id):
        return None
    try:
        element = doc.GetElement(element_id)
    except Exception:
        return None
    if isinstance(element, Wall):
        return element
    return None


def _append_face_candidates_from_geometry(doc, wall, geometry_object, view_frame,
                                          candidates, seen_keys):
    if geometry_object is None:
        return
    if isinstance(geometry_object, Solid):
        _append_face_candidates_from_solid(
            doc,
            wall,
            geometry_object,
            view_frame,
            candidates,
            seen_keys,
        )
        return
    if isinstance(geometry_object, GeometryInstance):
        try:
            nested_geometry = geometry_object.GetInstanceGeometry()
        except Exception:
            nested_geometry = None
        if nested_geometry is None:
            return
        for nested_object in nested_geometry:
            _append_face_candidates_from_geometry(
                doc,
                wall,
                nested_object,
                view_frame,
                candidates,
                seen_keys,
            )


def _append_face_candidates_from_solid(doc, wall, solid, view_frame,
                                       candidates, seen_keys):
    try:
        if solid.Volume <= 1e-9:
            return
    except Exception:
        pass
    try:
        faces = solid.Faces
    except Exception:
        return

    for face in faces:
        if not isinstance(face, PlanarFace):
            continue
        reference = getattr(face, "Reference", None)
        if reference is None:
            continue
        candidate = _face_candidate_from_face(doc, wall, face, reference, view_frame)
        if candidate is None:
            continue
        if candidate.stable_key in seen_keys:
            continue
        seen_keys.add(candidate.stable_key)
        candidates.append(candidate)


def _face_candidate_from_face(doc, wall, face, reference, view_frame):
    normal = _face_normal(face)
    if normal is None:
        return None
    axis_kind = utils.classify_direction(utils.vector_view_uv(normal, view_frame))
    if axis_kind == constants.DIRECTION_ALONG_U:
        axis = constants.AXIS_U
    elif axis_kind == constants.DIRECTION_ALONG_V:
        axis = constants.AXIS_V
    else:
        return None

    center = _face_center(face)
    if center is None:
        return None
    u_value, v_value = utils.project_to_uv(center, view_frame)
    coordinate = u_value if axis == constants.AXIS_U else v_value
    stable_key = utils.reference_stable_key(doc, reference)
    if not stable_key:
        stable_key = "wall-face:{0}:{1}:{2:.6f}".format(
            utils.safe_int_id(wall.Id),
            axis,
            coordinate,
        )
    return models.ReferenceCandidate(wall, reference, axis, coordinate, stable_key)


def _face_normal(face):
    try:
        return face.FaceNormal
    except Exception:
        pass
    try:
        bbox = face.GetBoundingBox()
        u_mid = 0.5 * (bbox.Min.U + bbox.Max.U)
        v_mid = 0.5 * (bbox.Min.V + bbox.Max.V)
        return face.ComputeNormal(UV(u_mid, v_mid))
    except Exception:
        return None


def _face_center(face):
    try:
        bbox = face.GetBoundingBox()
        u_mid = 0.5 * (bbox.Min.U + bbox.Max.U)
        v_mid = 0.5 * (bbox.Min.V + bbox.Max.V)
        return face.Evaluate(UV(u_mid, v_mid))
    except Exception:
        return None
