# -*- coding: utf-8 -*-
"""
Tool Name    : Auto Dimension
Purpose      : Central settings for automatic plan room, grid, and overall dimensions.
Author       : Ajmal P.S.
Company      : AJ Tools
Version      : 1.0.0
Created      : 2026-04-25
Last Updated : 2026-04-26
Target       : Revit 2020-2027
Platform     : pyRevit / IronPython
Dependencies : Python standard library
Input        : None
Output       : Shared constants for the Auto Dimension modules.
Notes        : Keep drafting offsets, tolerances, labels, and skip reasons here.
Changelog    : v1.0.1 - Added boundary-record group bucket and line-build skip constant.
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from __future__ import absolute_import, division, print_function


TOOL_NAME = "Auto Dimension"
TOOL_VERSION = "1.0.1"
TOOL_AUTHOR = "Ajmal P.S."
TOOL_COMPANY = "AJ Tools"

WINDOW_TITLE = "Auto Dimension"
REPORT_TITLE = "Auto Dimension - Report"
TRANSACTION_NAME = "Auto Dimension"


DEFAULT_OFFSET_MM = 8.0
MIN_OFFSET_MM = 2.0
MAX_OFFSET_MM = 50.0


# The user enters one paper-space offset. These rings keep exterior
# dimensions ordered: grid closer to the plan, overall outside grid.
OFFSET_RING_INTERNAL = 1.0
OFFSET_RING_GRID = 2.0
OFFSET_RING_OVERALL = 3.0


MM_PER_FOOT = 304.8
COINCIDENT_TOLERANCE_FT = 1.0 / 304.8
DIRECTION_BUCKET_TOLERANCE = 0.05
FACE_MATCH_TOLERANCE_MM = 90.0
FACE_FALLBACK_TOLERANCE_MM = 450.0
# Records that point to the same wall face but were split by an outside
# intersection may have a small physical gap between segments. We treat
# their face coordinates as the same when within this distance.
FACE_COORDINATE_GROUP_MM = 30.0
ROOM_LINE_PROBE_MM = 75.0
ROOM_LINE_END_INSET_MM = 80.0
ROOM_LINE_SAMPLE_COUNT = 5
MIN_ROOM_DIMENSION_MM = 300.0
MIN_GRID_SPACING_MM = 300.0
SIGNATURE_ROUND_DIGITS = 3


AXIS_U = "U"
AXIS_V = "V"
DIRECTION_ALONG_U = "ALONG_U"
DIRECTION_ALONG_V = "ALONG_V"
DIRECTION_OBLIQUE = "OBLIQUE"

SIDE_LOW = "LOW"
SIDE_HIGH = "HIGH"


SKIP_REASON_INVALID_ELEMENT = "Invalid Revit element"
SKIP_REASON_NO_LOCATION = "Element has no usable location"
SKIP_REASON_NON_ORTHOGONAL = "Element is not orthogonal to the active view axes"
SKIP_REASON_CURVED_GRID = "Curved grids are not supported for straight grid dimensions"
SKIP_REASON_NO_REFERENCE = "Could not get a stable Revit reference"
SKIP_REASON_NO_FACE_REFERENCE = "Could not find a usable wall face reference"
SKIP_REASON_HIDDEN = "Element is hidden in the active view"
SKIP_REASON_OUTSIDE_CROP = "Element or dimension line is outside the active view crop"
SKIP_REASON_CROP_MARGIN = "Not enough crop margin to place a readable outside dimension"
SKIP_REASON_NO_ROOM_BOUNDARY = "Room has no usable wall finish boundary"
SKIP_REASON_NO_OPPOSITE_FACES = "Could not find two opposite room-side wall face references"
SKIP_REASON_UNSAFE_ROOM_OFFSET = "Could not place the dimension line safely inside the room"
SKIP_REASON_TOO_SMALL = "Clear dimension span is too small"
SKIP_REASON_DUPLICATE_REFERENCE = "Duplicate reference at the same location"
SKIP_REASON_DUPLICATE_DIMENSION = "Matching dimension already exists in this view"
SKIP_REASON_NO_WALLS = "No visible host walls were found"
SKIP_REASON_NO_GRIDS = "No usable straight grids were found"
SKIP_REASON_API_FAILURE = "Revit could not create this dimension"
SKIP_REASON_LINE_BUILD_FAILED = "Dimension line could not be built"
