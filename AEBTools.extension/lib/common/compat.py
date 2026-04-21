"""
Tool Name    : Compatibility Dispatch Helpers
Purpose      : Resolve the correct version-specific helper namespace for a target Revit release
Author       : Ajmal P.S.
Company      : AJ Tools
Version      : 1.0.0
Created      : 2026-04-21
Last Updated : 2026-04-21
Target       : Revit 2020-2027
Platform     : pyRevit / Python
Dependencies : Python standard library, common.versioning
Input        : Revit version value
Output       : Version-specific module name or null-equivalent when unsupported
Notes        : Shared tools should prefer common modules first and branch only when required
Changelog    : v1.0.0 - Added standardized metadata header
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from common.versioning import normalize_version


def get_version_module_name(version_value):
    version = normalize_version(version_value)
    if not version:
        return None
    return "revit_{0}".format(version)
