# AEB Tools

Public install repository for the `AEBTools.extension` pyRevit extension for Autodesk Revit.

## Purpose

This repository is the release-ready install target for end users and secondary workstations. Development, testing, and release preparation happen in the private `PyRevit-Tools` workspace, then the validated extension is synced here.

## Supported Revit versions

- `2020` through `2027`

## Current toolset

- `Doors > Room to Door`
  Writes a selected writable text door parameter from associated room numbers with deterministic suffixing options.

## Requirements

- Windows workstation
- Autodesk Revit
- pyRevit installed and able to load custom extensions

## Install

1. Clone or download this repository to the target machine.
2. Keep `AEBTools.extension` at the repository root.
3. Add the repository root or the extension folder to pyRevit.
4. Reload pyRevit.
5. Confirm the `AEB Tools` tab appears in Revit.

## Update an existing installation

1. Pull the latest changes from this repository.
2. Reload pyRevit.
3. Re-run a quick smoke check in a non-production model after major updates.

## Repository contents

- `AEBTools.extension`: release-ready pyRevit extension content
- `VERSION`: current public release version
- `CHANGELOG.md`: notable release changes
- `RELEASE_NOTES.md`: current release summary

## Source and support

- Private source workspace: `PyRevit-Tools`
- Public install repo: `AEB-Tools`
- Issues and tracked work should be raised through GitHub
