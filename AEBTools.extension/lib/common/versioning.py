"""
Tool Name    : Revit Versioning Helpers
Purpose      : Normalize and validate supported Revit version values for extension workflows
Author       : Ajmal P.S.
Company      : AJ Tools
Version      : 1.0.0
Created      : 2026-04-21
Last Updated : 2026-04-21
Target       : Revit 2020-2027
Platform     : pyRevit / Python
Dependencies : Python standard library
Input        : Raw version values from configuration or runtime contexts
Output       : Normalized integers and support checks for Revit versions
Notes        : Used by compatibility routing and multi-version workspace checks
Changelog    : v1.0.0 - Added standardized metadata header
License      : All Rights Reserved
Repo         : AEB-Tools
"""

SUPPORTED_REVIT_VERSIONS = (2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027)
DEFAULT_BASELINE_VERSION = 2024


def normalize_version(version_value):
    try:
        return int(version_value)
    except (TypeError, ValueError):
        return None


def is_supported(version_value):
    version = normalize_version(version_value)
    return version in SUPPORTED_REVIT_VERSIONS
