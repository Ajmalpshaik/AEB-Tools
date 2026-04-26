# -*- coding: utf-8 -*-
"""
Tool Name    : Auto Dimension
Purpose      : Create clean internal room, external grid, and overall building dimensions.
Author       : Ajmal P.S.
Company      : AJ Tools
Version      : 1.0.0
Created      : 2026-04-25
Last Updated : 2026-04-26
Target       : Revit 2020-2027
Platform     : pyRevit / IronPython
Dependencies : Autodesk Revit API
Input        : Active plan view, rooms, grids, walls, selected options, offset, and dimension type.
Output       : ProcessReport with created/skipped counts and reasons.
Notes        : Uses view-aware and scale-safe dimension placement for stable BIM drafting output.
Changelog    : v1.0.1 - Outside-side wall splits no longer drop a room dimension axis.
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from __future__ import absolute_import, division, print_function

from Autodesk.Revit.DB import (
    Dimension,
    FilteredElementCollector,
    Line,
    Options,
    ReferenceArray,
    XYZ,
)

import collector
import constants
import models
import utils


def run(doc, view, view_frame, request):
    report = models.ProcessReport()
    report.dry_run = request.dry_run

    if not request.has_any_task():
        report.message = "No dimension options selected."
        return report

    context = _collect_context(doc, view, view_frame)
    wall_extents = _build_wall_extents(context["walls"], view_frame)
    building_box = collector.compute_building_uv_box(wall_extents)
    face_cache = {}
    existing_index = _build_existing_dimension_index(doc, view, view_frame)

    if request.dry_run:
        _run_dimension_tasks(
            doc,
            view,
            view_frame,
            request,
            context,
            wall_extents,
            building_box,
            face_cache,
            existing_index,
            report,
            False,
        )
        report.success = report.total_created() > 0
        report.message = "Dry run only. No dimensions were placed in the model."
        return report

    transaction = utils.safe_transaction(doc, constants.TRANSACTION_NAME)
    succeeded = False
    try:
        _run_dimension_tasks(
            doc,
            view,
            view_frame,
            request,
            context,
            wall_extents,
            building_box,
            face_cache,
            existing_index,
            report,
            True,
        )
        succeeded = True
    except Exception as run_error:
        report.message = "Auto Dimension failed: {0}".format(
            utils.clean_exception_message(run_error)
        )
        utils.commit_or_rollback(transaction, False)
        return report

    committed = utils.commit_or_rollback(transaction, succeeded)
    report.success = committed and report.total_created() > 0
    if not report.message:
        if report.total_created() == 0:
            report.message = "No dimensions were created. Review the skipped list for reasons."
        else:
            report.message = "Created {0} dimension(s) in one transaction.".format(
                report.total_created()
            )
    return report


def _run_dimension_tasks(doc, view, view_frame, request, context, wall_extents,
                         building_box, face_cache, existing_index, report,
                         create_dimension):
    if request.do_internal_rooms:
        report.add_outcome(_create_internal_room_dimensions(
            doc,
            view,
            view_frame,
            request,
            context["rooms"],
            wall_extents,
            face_cache,
            existing_index,
            create_dimension,
        ))

    if request.do_grids:
        report.add_outcome(_create_grid_dimensions(
            doc,
            view,
            view_frame,
            request,
            context["grids"],
            building_box,
            existing_index,
            create_dimension,
        ))

    if request.do_overall:
        report.add_outcome(_create_overall_dimensions(
            doc,
            view,
            view_frame,
            request,
            wall_extents,
            building_box,
            face_cache,
            existing_index,
            create_dimension,
        ))


def _collect_context(doc, view, view_frame):
    return {
        "walls": collector.collect_walls_in_view(doc, view, view_frame),
        "grids": collector.collect_grids_in_view(doc, view, view_frame),
        "rooms": collector.collect_rooms_in_view(doc, view, view_frame),
    }


def _build_wall_extents(walls, view_frame):
    extents = []
    for wall in walls:
        extent = collector.compute_wall_extent(wall, view_frame)
        if extent is not None:
            extents.append(extent)
    return utils.stable_sort(extents, lambda item: utils.safe_int_id(item.wall.Id))


# ---------------------------------------------------------------------------
# Internal room dimensions
# ---------------------------------------------------------------------------

def _create_internal_room_dimensions(doc, view, view_frame, request, rooms,
                                     wall_extents, face_cache, existing_index,
                                     create_dimension):
    outcome = models.TaskOutcome("Internal Room Dimensions")
    if not rooms:
        outcome.add_note("No valid rooms were found on the active view level.")
        return outcome
    if not wall_extents:
        outcome.add_note("Room dimensions skipped: {0}.".format(constants.SKIP_REASON_NO_WALLS))
        return outcome

    visible_wall_ids = set(utils.safe_int_id(extent.wall.Id) for extent in wall_extents)
    offset_ft = utils.offset_in_feet(
        request.offset_mm,
        constants.OFFSET_RING_INTERNAL,
        view_frame,
    )

    for room in rooms:
        room_id = utils.safe_int_id(room.Id)
        # Room boundary records are room-side finish boundaries. Exterior wall
        # sides with no placed room are intentionally not collected here.
        records = collector.collect_room_boundary_records(doc, room, view_frame)
        records = [
            record for record in records
            if utils.safe_int_id(record.wall.Id) in visible_wall_ids
        ]
        if not records:
            outcome.add_skipped("Room", room_id, constants.SKIP_REASON_NO_ROOM_BOUNDARY)
            continue

        u_spec, u_reason = _build_room_axis_dimension_spec(
            doc,
            view,
            view_frame,
            room,
            records,
            constants.AXIS_U,
            offset_ft,
            face_cache,
        )
        v_spec, v_reason = _build_room_axis_dimension_spec(
            doc,
            view,
            view_frame,
            room,
            records,
            constants.AXIS_V,
            offset_ft,
            face_cache,
        )

        _name_room_axis_specs(room, u_spec, v_spec)

        if u_spec is not None:
            _try_dimension_from_spec(
                doc,
                view,
                request,
                u_spec,
                outcome,
                existing_index,
                create_dimension,
            )
        else:
            outcome.add_skipped(
                "Room",
                room_id,
                "View-right internal dimension: {0}".format(u_reason),
            )

        if v_spec is not None:
            _try_dimension_from_spec(
                doc,
                view,
                request,
                v_spec,
                outcome,
                existing_index,
                create_dimension,
            )
        else:
            outcome.add_skipped(
                "Room",
                room_id,
                "View-up internal dimension: {0}".format(v_reason),
            )

    if outcome.created_count == 0 and not outcome.skipped_items and not outcome.notes:
        outcome.add_note("No safe internal room dimensions could be created.")
    return outcome


def _build_room_axis_dimension_spec(doc, view, view_frame, room, records, axis,
                                    offset_ft, face_cache):
    base_records = [record for record in records if record.segment_axis == axis]
    ref_records = [record for record in records if record.face_axis == axis]
    if not base_records:
        return None, "No parallel room boundary was found for placement."
    if len(ref_records) < 2:
        return None, constants.SKIP_REASON_NO_OPPOSITE_FACES

    base_records = _sort_room_base_records_for_axis(base_records, axis)
    last_reason = constants.SKIP_REASON_UNSAFE_ROOM_OFFSET

    for base_record in base_records:
        inside_sign = _room_inside_sign(base_record, view_frame, offset_ft)
        if inside_sign == 0:
            last_reason = constants.SKIP_REASON_UNSAFE_ROOM_OFFSET
            continue

        line_constant = base_record.face_coordinate + inside_sign * offset_ft
        candidates = _room_axis_reference_candidates(
            doc,
            view,
            view_frame,
            ref_records,
            axis,
            line_constant,
            offset_ft,
            face_cache,
        )
        if len(candidates) < 2:
            last_reason = constants.SKIP_REASON_NO_OPPOSITE_FACES
            continue

        pair = _best_room_axis_candidate_pair(
            room,
            axis,
            line_constant,
            candidates,
            view_frame,
        )
        if pair is None:
            last_reason = constants.SKIP_REASON_UNSAFE_ROOM_OFFSET
            continue

        low_candidate, high_candidate = pair
        start_value = min(low_candidate.coordinate, high_candidate.coordinate)
        end_value = max(low_candidate.coordinate, high_candidate.coordinate)
        span = end_value - start_value
        if span < utils.mm_to_feet(constants.MIN_ROOM_DIMENSION_MM):
            last_reason = constants.SKIP_REASON_TOO_SMALL
            continue

        if not utils.line_inside_crop(axis, start_value, end_value, line_constant, view_frame):
            last_reason = constants.SKIP_REASON_OUTSIDE_CROP
            continue

        line = utils.make_axis_line(
            axis,
            start_value,
            end_value,
            line_constant,
            view_frame,
            _room_location_point(room),
        )
        if line is None:
            last_reason = constants.SKIP_REASON_LINE_BUILD_FAILED
            continue

        spec = models.DimensionSpec(
            "Room {0} {1}".format(_room_display_label(room), axis),
            "Room",
            utils.safe_int_id(room.Id),
            axis,
            line_constant,
            line,
            [low_candidate, high_candidate],
            span,
        )
        return spec, None

    return None, last_reason


def _sort_room_base_records_for_axis(base_records, axis):
    if axis == constants.AXIS_U:
        return utils.stable_sort(
            base_records,
            lambda item: (-round(item.face_coordinate, 6),
                          -round(item.length, 6),
                          utils.safe_int_id(item.wall.Id)),
        )
    return utils.stable_sort(
        base_records,
        lambda item: (round(item.face_coordinate, 6),
                      -round(item.length, 6),
                      utils.safe_int_id(item.wall.Id)),
    )


def _room_axis_reference_candidates(doc, view, view_frame, ref_records, axis,
                                    line_constant, offset_ft, face_cache):
    candidates = []
    seen_coordinates = []
    for record in ref_records:
        if not _record_crosses_dimension_line(record, line_constant):
            continue
        candidate = _inside_face_candidate_for_boundary_record(
            doc,
            view,
            view_frame,
            record,
            offset_ft,
            face_cache,
        )
        if candidate is None:
            continue
        if candidate.axis != axis:
            continue
        if _has_near_coordinate(seen_coordinates, candidate.coordinate):
            continue
        seen_coordinates.append(candidate.coordinate)
        candidates.append(candidate)
    return utils.stable_sort(
        candidates,
        lambda item: (round(item.coordinate, 6), item.stable_key),
    )


def _record_crosses_dimension_line(record, line_constant):
    # The boundary record is already consolidated across split segments at
    # this point, so a small probe tolerance is enough to absorb float drift.
    tolerance = utils.mm_to_feet(constants.ROOM_LINE_PROBE_MM)
    return (record.along_min - tolerance
            <= line_constant
            <= record.along_max + tolerance)


def _best_room_axis_candidate_pair(room, axis, line_constant, candidates, view_frame):
    pairs = []
    for low_index in range(len(candidates) - 1):
        for high_index in range(low_index + 1, len(candidates)):
            low_candidate = candidates[low_index]
            high_candidate = candidates[high_index]
            start_value = min(low_candidate.coordinate, high_candidate.coordinate)
            end_value = max(low_candidate.coordinate, high_candidate.coordinate)
            span = end_value - start_value
            if span < utils.mm_to_feet(constants.MIN_ROOM_DIMENSION_MM):
                continue
            if not _room_axis_line_is_inside(
                    room,
                    axis,
                    start_value,
                    end_value,
                    line_constant,
                    view_frame):
                continue
            pairs.append((span, low_candidate.stable_key, high_candidate.stable_key,
                          low_candidate, high_candidate))

    if not pairs:
        return None

    pairs = utils.stable_sort(
        pairs,
        lambda item: (-round(item[0], 6), item[1], item[2]),
    )
    return pairs[0][3], pairs[0][4]


def _name_room_axis_specs(room, u_spec, v_spec):
    room_label = _room_display_label(room)
    if u_spec is not None and v_spec is not None:
        if u_spec.span_length <= v_spec.span_length:
            u_spec.label = "Room {0} width".format(room_label)
            v_spec.label = "Room {0} length".format(room_label)
        else:
            u_spec.label = "Room {0} length".format(room_label)
            v_spec.label = "Room {0} width".format(room_label)
        return

    if u_spec is not None:
        u_spec.label = "Room {0} view-right dimension".format(room_label)
    if v_spec is not None:
        v_spec.label = "Room {0} view-up dimension".format(room_label)


def _room_axis_line_is_inside(room, axis, start_value, end_value,
                              line_constant, view_frame):
    sample_values = _line_sample_values(start_value, end_value)
    anchor = _room_location_point(room)
    for sample_value in sample_values:
        point = utils.axis_point_to_world(
            axis,
            sample_value,
            line_constant,
            view_frame,
            anchor,
        )
        if not _room_contains_point(room, point):
            return False
    return True


def _room_inside_sign(record, view_frame, offset_ft):
    probe_ft = max(
        utils.mm_to_feet(constants.ROOM_LINE_PROBE_MM),
        min(offset_ft, utils.mm_to_feet(300.0)),
    )
    positive = _room_contains_boundary_offset(record, 1, probe_ft, view_frame)
    negative = _room_contains_boundary_offset(record, -1, probe_ft, view_frame)
    if positive and not negative:
        return 1
    if negative and not positive:
        return -1
    if positive and negative:
        room_point = _room_location_point(record.room)
        if room_point is not None:
            room_u, room_v = utils.project_to_uv(room_point, view_frame)
            room_coord = room_v if record.face_axis == constants.AXIS_V else room_u
            if room_coord >= record.face_coordinate:
                return 1
            return -1
    return 0


def _room_contains_boundary_offset(record, side_sign, distance_ft, view_frame):
    anchor = _room_location_point(record.room)
    for along_value in _record_sample_values(record):
        if record.segment_axis == constants.AXIS_U:
            point = utils.uv_to_world(
                along_value,
                record.face_coordinate + side_sign * distance_ft,
                view_frame,
                anchor,
            )
        else:
            point = utils.uv_to_world(
                record.face_coordinate + side_sign * distance_ft,
                along_value,
                view_frame,
                anchor,
            )
        if not _room_contains_point(record.room, point):
            return False
    return True


def _record_sample_values(record):
    return _line_sample_values(record.along_min, record.along_max)


def _line_sample_values(start_value, end_value):
    low_value = min(start_value, end_value)
    high_value = max(start_value, end_value)
    span = high_value - low_value
    if span <= utils.mm_to_feet(constants.ROOM_LINE_END_INSET_MM * 2.0):
        return [0.5 * (low_value + high_value)]

    inset = min(utils.mm_to_feet(constants.ROOM_LINE_END_INSET_MM), span * 0.2)
    sample_start = low_value + inset
    sample_end = high_value - inset
    count = max(2, int(constants.ROOM_LINE_SAMPLE_COUNT))
    values = []
    for index in range(count):
        fraction = float(index) / float(count - 1)
        values.append(sample_start + (sample_end - sample_start) * fraction)
    return values


def _inside_face_candidate_for_boundary_record(doc, view, view_frame, record,
                                               offset_ft, face_cache):
    candidates = [
        candidate for candidate in _face_candidates_for_wall(
            doc,
            record.wall,
            view,
            view_frame,
            face_cache,
        )
        if candidate.axis == record.face_axis
    ]
    if not candidates:
        return None

    tolerance = utils.mm_to_feet(constants.FACE_MATCH_TOLERANCE_MM)
    candidates = utils.stable_sort(
        candidates,
        lambda item: (abs(item.coordinate - record.face_coordinate), item.stable_key),
    )
    if abs(candidates[0].coordinate - record.face_coordinate) <= tolerance:
        return candidates[0]

    inside_sign = _room_inside_sign(record, view_frame, offset_ft)
    if inside_sign == 0:
        return None

    fallback_tolerance = utils.mm_to_feet(constants.FACE_FALLBACK_TOLERANCE_MM)
    if inside_sign > 0:
        room_side_candidate = max(
            candidates,
            key=lambda item: (item.coordinate, item.stable_key),
        )
    else:
        room_side_candidate = min(
            candidates,
            key=lambda item: (item.coordinate, item.stable_key),
        )

    if abs(room_side_candidate.coordinate - record.face_coordinate) <= fallback_tolerance:
        return room_side_candidate
    return None


def _room_contains_point(room, point):
    if room is None or point is None:
        return False

    probe_points = [point]
    room_point = _room_location_point(room)
    if room_point is not None:
        try:
            probe_points.append(XYZ(point.X, point.Y, room_point.Z + utils.mm_to_feet(50.0)))
            probe_points.append(XYZ(point.X, point.Y, room_point.Z + utils.mm_to_feet(1200.0)))
        except Exception:
            pass
    try:
        probe_points.append(point + XYZ.BasisZ.Multiply(utils.mm_to_feet(1200.0)))
    except Exception:
        pass

    for probe_point in probe_points:
        try:
            if room.IsPointInRoom(probe_point):
                return True
        except Exception:
            continue
    return False


def _room_location_point(room):
    try:
        return room.Location.Point
    except Exception:
        return None


def _room_display_label(room):
    try:
        number = room.Number
    except Exception:
        number = ""
    if number:
        return number
    return str(utils.safe_int_id(room.Id))


# ---------------------------------------------------------------------------
# External grid dimensions
# ---------------------------------------------------------------------------

def _create_grid_dimensions(doc, view, view_frame, request, grids, building_box,
                            existing_index, create_dimension):
    outcome = models.TaskOutcome("External Grid Dimensions")
    vertical_grids = []
    horizontal_grids = []

    for grid in grids:
        bucket, position, reason = _grid_bucket_and_position(grid, view_frame)
        if bucket is None:
            outcome.add_skipped("Grid", utils.safe_int_id(grid.Id), reason)
            continue
        if bucket == constants.DIRECTION_ALONG_V:
            vertical_grids.append((grid, position))
        else:
            horizontal_grids.append((grid, position))

    if not vertical_grids and not horizontal_grids:
        outcome.add_note(constants.SKIP_REASON_NO_GRIDS)
        return outcome

    placement_box = building_box
    if placement_box is None:
        placement_box = collector.compute_grid_uv_box(grids, view_frame)
    if placement_box is None:
        outcome.add_note("Grid dimensions skipped: no placement extents were available.")
        return outcome

    max_ring = constants.OFFSET_RING_OVERALL if request.do_overall else constants.OFFSET_RING_GRID
    max_offset = utils.offset_in_feet(request.offset_mm, max_ring, view_frame)
    grid_offset = utils.offset_in_feet(
        request.offset_mm,
        constants.OFFSET_RING_GRID,
        view_frame,
    )

    if len(vertical_grids) >= 2:
        _create_grid_chain(
            doc,
            view,
            view_frame,
            request,
            outcome,
            vertical_grids,
            constants.AXIS_U,
            placement_box,
            grid_offset,
            max_offset,
            existing_index,
            create_dimension,
        )
    elif vertical_grids:
        outcome.add_note("Horizontal grid chain skipped: fewer than two vertical grids.")

    if len(horizontal_grids) >= 2:
        _create_grid_chain(
            doc,
            view,
            view_frame,
            request,
            outcome,
            horizontal_grids,
            constants.AXIS_V,
            placement_box,
            grid_offset,
            max_offset,
            existing_index,
            create_dimension,
        )
    elif horizontal_grids:
        outcome.add_note("Vertical grid chain skipped: fewer than two horizontal grids.")

    return outcome


def _create_grid_chain(doc, view, view_frame, request, outcome, grid_pairs,
                       axis, placement_box, offset_ft, max_offset_ft,
                       existing_index, create_dimension):
    grid_pairs = utils.stable_sort(
        grid_pairs,
        lambda item: (round(item[1], 6), utils.safe_int_id(item[0].Id)),
    )
    start_value = grid_pairs[0][1]
    end_value = grid_pairs[-1][1]
    if abs(end_value - start_value) < utils.mm_to_feet(constants.MIN_GRID_SPACING_MM):
        outcome.add_note("Grid chain skipped: {0}.".format(constants.SKIP_REASON_TOO_SMALL))
        return

    outside_axis = utils.perpendicular_axis(axis)
    outside_lo, outside_hi = _box_axis_range(placement_box, outside_axis)
    side = _select_outside_side(outside_axis, outside_lo, outside_hi, max_offset_ft, view_frame)
    if side is None:
        outcome.add_note("Grid chain skipped: {0}.".format(constants.SKIP_REASON_CROP_MARGIN))
        return

    line_constant = _outside_coordinate(outside_lo, outside_hi, offset_ft, side)
    if not utils.line_inside_crop(axis, start_value, end_value, line_constant, view_frame):
        outcome.add_note("Grid chain skipped: {0}.".format(constants.SKIP_REASON_OUTSIDE_CROP))
        return

    candidates = _grid_reference_candidates(doc, view, grid_pairs, axis, outcome)
    line = utils.make_axis_line(
        axis,
        start_value,
        end_value,
        line_constant,
        view_frame,
        view_frame.origin,
    )
    label = "Grid horizontal chain" if axis == constants.AXIS_U else "Grid vertical chain"
    spec = models.DimensionSpec(
        label,
        "Grid",
        0,
        axis,
        line_constant,
        line,
        candidates,
        abs(end_value - start_value),
    )
    _try_dimension_from_spec(
        doc,
        view,
        request,
        spec,
        outcome,
        existing_index,
        create_dimension,
    )


def _grid_bucket_and_position(grid, view_frame):
    curve = collector.get_grid_line(grid)
    if curve is None:
        return None, 0.0, constants.SKIP_REASON_CURVED_GRID
    try:
        start = curve.GetEndPoint(0)
        end = curve.GetEndPoint(1)
    except Exception:
        return None, 0.0, constants.SKIP_REASON_NO_LOCATION

    direction_kind = utils.classify_direction(utils.vector_view_uv(end - start, view_frame))
    start_u, start_v = utils.project_to_uv(start, view_frame)
    end_u, end_v = utils.project_to_uv(end, view_frame)
    if direction_kind == constants.DIRECTION_ALONG_V:
        return direction_kind, 0.5 * (start_u + end_u), None
    if direction_kind == constants.DIRECTION_ALONG_U:
        return direction_kind, 0.5 * (start_v + end_v), None
    return None, 0.0, constants.SKIP_REASON_NON_ORTHOGONAL


def _grid_reference_candidates(doc, view, grid_pairs, axis, outcome):
    candidates = []
    for grid, position in grid_pairs:
        reference = _grid_reference(grid, view)
        if reference is None:
            outcome.add_skipped("Grid", utils.safe_int_id(grid.Id), constants.SKIP_REASON_NO_REFERENCE)
            continue
        stable_key = utils.reference_stable_key(doc, reference)
        if not stable_key:
            stable_key = "grid:{0}".format(utils.safe_int_id(grid.Id))
        candidates.append(models.ReferenceCandidate(
            grid,
            reference,
            axis,
            position,
            stable_key,
        ))
    return candidates


def _grid_reference(grid, view):
    try:
        reference = grid.Curve.Reference
        if reference is not None:
            return reference
    except Exception:
        pass

    options = Options()
    options.View = view
    options.ComputeReferences = True
    options.IncludeNonVisibleObjects = False
    try:
        geometry_element = grid.get_Geometry(options)
    except Exception:
        geometry_element = None
    if geometry_element is None:
        return None
    for geometry_object in geometry_element:
        try:
            if isinstance(geometry_object, Line) and geometry_object.Reference is not None:
                return geometry_object.Reference
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Overall building dimensions
# ---------------------------------------------------------------------------

def _create_overall_dimensions(doc, view, view_frame, request, wall_extents,
                               building_box, face_cache, existing_index,
                               create_dimension):
    outcome = models.TaskOutcome("Overall Building Dimensions")
    if building_box is None:
        outcome.add_note("Overall dimensions skipped: {0}.".format(constants.SKIP_REASON_NO_WALLS))
        return outcome

    offset_ft = utils.offset_in_feet(
        request.offset_mm,
        constants.OFFSET_RING_OVERALL,
        view_frame,
    )

    _create_overall_axis_dimension(
        doc,
        view,
        view_frame,
        request,
        outcome,
        wall_extents,
        building_box,
        constants.AXIS_U,
        offset_ft,
        face_cache,
        existing_index,
        create_dimension,
    )
    _create_overall_axis_dimension(
        doc,
        view,
        view_frame,
        request,
        outcome,
        wall_extents,
        building_box,
        constants.AXIS_V,
        offset_ft,
        face_cache,
        existing_index,
        create_dimension,
    )

    if outcome.created_count == 0 and not outcome.skipped_items:
        outcome.add_note("No overall dimensions could be created.")
    return outcome


def _create_overall_axis_dimension(doc, view, view_frame, request, outcome,
                                   wall_extents, building_box, axis, offset_ft,
                                   face_cache, existing_index, create_dimension):
    candidates = _face_candidates_for_extents(
        doc,
        view,
        view_frame,
        wall_extents,
        face_cache,
        axis,
    )
    low_candidate, high_candidate = _extreme_face_pair(candidates)
    if low_candidate is None or high_candidate is None:
        outcome.add_note("Overall {0} skipped: fewer than two wall face references.".format(axis))
        return

    outside_axis = utils.perpendicular_axis(axis)
    outside_lo, outside_hi = _box_axis_range(building_box, outside_axis)
    side = _select_outside_side(outside_axis, outside_lo, outside_hi, offset_ft, view_frame)
    if side is None:
        outcome.add_note("Overall {0} skipped: {1}.".format(
            axis,
            constants.SKIP_REASON_CROP_MARGIN,
        ))
        return

    line_constant = _outside_coordinate(outside_lo, outside_hi, offset_ft, side)
    start_value = low_candidate.coordinate
    end_value = high_candidate.coordinate
    if not utils.line_inside_crop(axis, start_value, end_value, line_constant, view_frame):
        outcome.add_note("Overall {0} skipped: {1}.".format(
            axis,
            constants.SKIP_REASON_OUTSIDE_CROP,
        ))
        return

    line = utils.make_axis_line(
        axis,
        start_value,
        end_value,
        line_constant,
        view_frame,
        view_frame.origin,
    )
    label = "Overall horizontal" if axis == constants.AXIS_U else "Overall vertical"
    spec = models.DimensionSpec(
        label,
        "Overall",
        0,
        axis,
        line_constant,
        line,
        [low_candidate, high_candidate],
        abs(end_value - start_value),
    )
    _try_dimension_from_spec(
        doc,
        view,
        request,
        spec,
        outcome,
        existing_index,
        create_dimension,
    )


# ---------------------------------------------------------------------------
# Shared reference, placement, and creation helpers
# ---------------------------------------------------------------------------

def _face_candidates_for_wall(doc, wall, view, view_frame, face_cache):
    wall_id = utils.safe_int_id(wall.Id)
    if wall_id not in face_cache:
        face_cache[wall_id] = collector.collect_wall_face_candidates(
            doc,
            wall,
            view,
            view_frame,
        )
    return face_cache[wall_id]


def _face_candidates_for_extents(doc, view, view_frame, wall_extents,
                                 face_cache, axis):
    candidates = []
    for extent in wall_extents:
        wall_candidates = _face_candidates_for_wall(
            doc,
            extent.wall,
            view,
            view_frame,
            face_cache,
        )
        for candidate in wall_candidates:
            if candidate.axis == axis:
                candidates.append(candidate)
    return utils.stable_sort(
        candidates,
        lambda item: (round(item.coordinate, 6), item.stable_key),
    )


def _extreme_face_pair(candidates):
    if len(candidates) < 2:
        return None, None
    low_candidate = min(candidates, key=lambda item: (item.coordinate, item.stable_key))
    high_candidate = max(candidates, key=lambda item: (item.coordinate, item.stable_key))
    if utils.near_equal(low_candidate.coordinate, high_candidate.coordinate):
        return None, None
    return low_candidate, high_candidate


def _box_axis_range(uv_box, axis):
    if axis == constants.AXIS_U:
        return uv_box[0], uv_box[1]
    return uv_box[2], uv_box[3]


def _select_outside_side(axis, low_value, high_value, offset_ft, view_frame):
    crop = getattr(view_frame, "crop_box", None)
    if crop is None:
        return constants.SIDE_LOW

    if axis == constants.AXIS_U:
        crop_low = crop.u_lo
        crop_high = crop.u_hi
    else:
        crop_low = crop.v_lo
        crop_high = crop.v_hi

    if low_value - offset_ft >= crop_low:
        return constants.SIDE_LOW
    if high_value + offset_ft <= crop_high:
        return constants.SIDE_HIGH
    return None


def _outside_coordinate(low_value, high_value, offset_ft, side):
    if side == constants.SIDE_HIGH:
        return high_value + offset_ft
    return low_value - offset_ft


def _reference_array_from_candidates(candidates, outcome, category_label):
    refs = ReferenceArray()
    ref_keys = []
    seen_keys = set()
    seen_coordinates = []

    candidates = utils.stable_sort(
        candidates,
        lambda item: (round(item.coordinate, 6), item.stable_key),
    )
    for candidate in candidates:
        if candidate.reference is None:
            outcome.add_skipped(
                category_label,
                utils.safe_int_id(candidate.element.Id),
                constants.SKIP_REASON_NO_REFERENCE,
            )
            continue
        if candidate.stable_key in seen_keys:
            outcome.add_skipped(
                category_label,
                utils.safe_int_id(candidate.element.Id),
                constants.SKIP_REASON_DUPLICATE_REFERENCE,
            )
            continue
        if _has_near_coordinate(seen_coordinates, candidate.coordinate):
            outcome.add_skipped(
                category_label,
                utils.safe_int_id(candidate.element.Id),
                constants.SKIP_REASON_DUPLICATE_REFERENCE,
            )
            continue
        refs.Append(candidate.reference)
        ref_keys.append(candidate.stable_key)
        seen_keys.add(candidate.stable_key)
        seen_coordinates.append(candidate.coordinate)

    if len(ref_keys) < 2:
        return None, []
    return refs, ref_keys


def _has_near_coordinate(coordinates, coordinate):
    for existing in coordinates:
        if utils.near_equal(existing, coordinate):
            return True
    return False


def _try_dimension_from_spec(doc, view, request, spec, outcome,
                             existing_index, create_dimension):
    if spec is None:
        return None
    if spec.line is None:
        outcome.add_skipped(
            spec.category,
            spec.element_id,
            constants.SKIP_REASON_LINE_BUILD_FAILED,
        )
        return None

    refs, ref_keys = _reference_array_from_candidates(
        spec.candidates,
        outcome,
        spec.category,
    )
    if refs is None or len(ref_keys) < 2:
        outcome.add_skipped(spec.category, spec.element_id, constants.SKIP_REASON_NO_REFERENCE)
        return None

    signature = _dimension_signature(spec.axis, spec.line_constant, ref_keys)
    if signature in existing_index:
        outcome.add_skipped(spec.category, spec.element_id, constants.SKIP_REASON_DUPLICATE_DIMENSION)
        return None

    if not create_dimension:
        existing_index.add(signature)
        outcome.add_created(1)
        return None

    try:
        dim_type = _resolve_dimension_type(doc, request)
        if dim_type is not None:
            dimension = doc.Create.NewDimension(view, spec.line, refs, dim_type)
        else:
            dimension = doc.Create.NewDimension(view, spec.line, refs)
    except Exception as create_error:
        outcome.add_skipped(
            spec.category,
            spec.element_id,
            "{0}: {1}".format(
                constants.SKIP_REASON_API_FAILURE,
                utils.clean_exception_message(create_error),
            ),
        )
        return None

    if dimension is None:
        outcome.add_skipped(spec.category, spec.element_id, constants.SKIP_REASON_API_FAILURE)
        return None

    existing_index.add(signature)
    outcome.add_created(1)
    return dimension


def _resolve_dimension_type(doc, request):
    if request.dimension_type_id is None:
        return None
    if utils.is_invalid_id(request.dimension_type_id):
        return None
    try:
        return doc.GetElement(request.dimension_type_id)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Existing-dimension duplicate prevention
# ---------------------------------------------------------------------------

def _build_existing_dimension_index(doc, view, view_frame):
    signatures = set()
    try:
        dimensions = (
            FilteredElementCollector(doc, view.Id)
            .OfClass(Dimension)
            .WhereElementIsNotElementType()
        )
    except Exception:
        return signatures

    for dimension in dimensions:
        axis, line_constant = _dimension_axis_and_constant(dimension, view_frame)
        if axis is None:
            continue
        ref_keys = _dimension_reference_keys(doc, dimension)
        if len(ref_keys) < 2:
            continue
        signatures.add(_dimension_signature(axis, line_constant, ref_keys))
    return signatures


def _dimension_axis_and_constant(dimension, view_frame):
    try:
        curve = dimension.Curve
        start = curve.GetEndPoint(0)
        end = curve.GetEndPoint(1)
    except Exception:
        return None, 0.0
    direction_kind = utils.classify_direction(utils.vector_view_uv(end - start, view_frame))
    start_u, start_v = utils.project_to_uv(start, view_frame)
    end_u, end_v = utils.project_to_uv(end, view_frame)
    if direction_kind == constants.DIRECTION_ALONG_U:
        return constants.AXIS_U, 0.5 * (start_v + end_v)
    if direction_kind == constants.DIRECTION_ALONG_V:
        return constants.AXIS_V, 0.5 * (start_u + end_u)
    return None, 0.0


def _dimension_reference_keys(doc, dimension):
    try:
        refs = dimension.References
    except Exception:
        return []
    keys = []
    for reference in _iter_reference_array(refs):
        key = utils.reference_stable_key(doc, reference)
        if key:
            keys.append(key)
    return keys


def _iter_reference_array(refs):
    if refs is None:
        return
    try:
        iterator = refs.ForwardIterator()
    except Exception:
        iterator = None

    if iterator is not None:
        try:
            iterator.Reset()
            while iterator.MoveNext():
                yield iterator.Current
            return
        except Exception:
            pass

    try:
        for reference in refs:
            yield reference
    except Exception:
        return


def _dimension_signature(axis, line_constant, ref_keys):
    rounded_constant = round(float(line_constant), constants.SIGNATURE_ROUND_DIGITS)
    sorted_keys = tuple(sorted([key for key in ref_keys if key]))
    return (axis, rounded_constant, sorted_keys)
