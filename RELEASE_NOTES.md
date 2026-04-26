# Release Notes

## 1.1.3 - 2026-04-26

### Included commands

- `Doors > Room to Door`
- `Doors > Mirror Door`
- `Dimensions > Auto Plan Dimension`

### Release updates

- Synced the `Dimensions.panel/Auto Plan Dimension.pushbutton` runtime bundle into the public install repository.
- Updated public release metadata to version `1.1.3`.

## 1.1.2 - 2026-04-26

### Included commands

- `Doors > Room to Door`
- `Doors > Mirror Door`

### Release updates

- Added beginner-safe Git workflow guidance in `README.md` to help new maintainers avoid risky Git commands.
- Updated public release metadata to version `1.1.2`.

## 1.1.1 - 2026-04-25

### Included commands

- `Doors > Room to Door`
- `Doors > Mirror Door`

### Supported Revit versions

- `2020` through `2027`

### Install package source

- `AEBTools.extension`

### Functional updates

- `Room to Door` now ships the current facing-side and opposite-side workflow with guarded `ToRoom` and `FromRoom` fallback behavior
- `Mirror Door` is now packaged under its shipped command name instead of the older `Identify Mirrored Doors` bundle name
- The public install package now contains only the active runtime bundles, shared libraries, and required extension metadata

### GitHub delivery updates

- Public validation now checks the shipped `Mirror Door` bundle path and the cleaned runtime-only extension layout
- Public release publishing continues through the tag-driven GitHub Actions package workflow

### Delivery note

This public repo is generated from the validated private `PyRevit-Tools` workspace.
