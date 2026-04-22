# AEB Tools

[![Validate Public Repo](https://github.com/Ajmalpshaik/AEB-Tools/actions/workflows/validate-public-repo.yml/badge.svg)](https://github.com/Ajmalpshaik/AEB-Tools/actions/workflows/validate-public-repo.yml)
[![Release Package](https://github.com/Ajmalpshaik/AEB-Tools/actions/workflows/release-package.yml/badge.svg)](https://github.com/Ajmalpshaik/AEB-Tools/actions/workflows/release-package.yml)
[![Latest Release](https://img.shields.io/github/v/release/Ajmalpshaik/AEB-Tools?display_name=tag)](https://github.com/Ajmalpshaik/AEB-Tools/releases)

Public install repository for the `AEBTools.extension` pyRevit extension for Autodesk Revit.

This repository is intended for installation, updates, and day-to-day use. Development, QA, and workspace automation are maintained separately in the private source workspace.

## Included Tool

### Room to Door

Updates a user-selected writable door parameter from the associated room number. The command supports active view, current selection, and whole-project processing with alphabetic or numeric suffixing.

## Supported Revit Versions

Validated for `Revit 2020` through `Revit 2027`.

## Install

### Option 1: Download the latest release

1. Open the [Releases](https://github.com/Ajmalpshaik/AEB-Tools/releases) page.
2. Download the latest `AEB-Tools-vX.Y.Z.zip` package.
3. Extract the ZIP to a stable local folder.
4. Keep the `AEBTools.extension` folder name unchanged.
5. In Revit, open `pyRevit Settings`.
6. Add the extracted repository root folder or the `AEBTools.extension` folder as a custom extension path.
7. Reload pyRevit and confirm that the `AEB Tools` tab appears.

### Option 2: Clone the repository

```powershell
git clone https://github.com/Ajmalpshaik/AEB-Tools.git
```

After cloning, add the repository root or the `AEBTools.extension` folder to pyRevit and reload pyRevit.

## Update

1. Download the latest release package or pull the latest `main` branch changes.
2. Replace the previous public install files with the new version.
3. Reload pyRevit.
4. Validate the command in a test model before using it on live project work.

## Release Packaging

GitHub Actions validates public release metadata on every push and pull request.

Tagged releases also generate a versioned ZIP package that contains:

- `AEBTools.extension`
- `README.md`
- `CHANGELOG.md`
- `RELEASE_NOTES.md`
- `VERSION`

## Repository Contents

- `AEBTools.extension` - pyRevit extension files for installation
- `README.md` - install and usage guide
- `CHANGELOG.md` - public release history
- `RELEASE_NOTES.md` - latest public release summary
- `VERSION` - current public package version

## Support

Use this repository for installation and updates. If a released package has a reproducible issue, open a GitHub issue with the Revit version, pyRevit version, and a short reproduction note.
