# Changelog

## [Unreleased]

- Reserved for upcoming public release changes.

## [1.1.2] - 2026-04-26

- Added a beginner-safe Git workflow section to `README.md` for safe pull, stage, commit, and push steps.
- Updated release metadata files (`VERSION`, `README.md`, and `RELEASE_NOTES.md`) for `1.1.2`.

## [1.1.1] - 2026-04-25

- Synced the cleaned `1.1.1` release package from the validated private `PyRevit-Tools` workspace.
- Renamed the shipped mirrored-door command bundle from `Identify Mirrored Doors` to `Mirror Door` to match the Revit UI.
- Updated `Room to Door` to use the current facing-side and opposite-side workflow with guarded `ToRoom` and `FromRoom` fallback behavior.
- Removed bundle-local README files, starter template bundles, empty placeholder folders, and unused version-stub packages from the public install package.
- Updated public release metadata and validation rules to match the runtime-only extension layout.

## [1.1.0] - 2026-04-22

- Added the `Mirror Door` production command to the public install package
- Updated `Room to Door` with door-side room-source selection and legacy fallback behavior
- Synced the refreshed shared helper layer from the private `PyRevit-Tools` workspace

## [1.0.2] - 2026-04-22

- Added GitHub Actions validation for public release metadata
- Added automated ZIP packaging for tagged GitHub releases
- Refreshed the public README with release-based installation guidance

## [1.0.1] - 2026-04-21

- Initial public install baseline for `AEB Tools`
- Includes the `Room to Door` production command
- Synced from the private `PyRevit-Tools` workspace
