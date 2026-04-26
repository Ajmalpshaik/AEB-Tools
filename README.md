# AEB Tools

[![Validate Public Repo](https://github.com/Ajmalpshaik/AEB-Tools/actions/workflows/validate-public-repo.yml/badge.svg)](https://github.com/Ajmalpshaik/AEB-Tools/actions/workflows/validate-public-repo.yml)
[![Release Package](https://github.com/Ajmalpshaik/AEB-Tools/actions/workflows/release-package.yml/badge.svg)](https://github.com/Ajmalpshaik/AEB-Tools/actions/workflows/release-package.yml)
[![Latest Release](https://img.shields.io/github/v/release/Ajmalpshaik/AEB-Tools?display_name=tag)](https://github.com/Ajmalpshaik/AEB-Tools/releases)

Public install repository for the `AEBTools.extension` pyRevit extension for Autodesk Revit.

This repository is intended for installation, updates, and day-to-day use. Development, QA, and workspace automation are maintained separately in the private source workspace.

- Current public package version: `1.1.3`
- Maintainer: `Ajmal P.S.`

## Included Tools

### Room to Door

Updates a user-selected writable door parameter from the associated room number. The command supports active view, current selection, whole-project processing, facing-side or opposite-side room resolution, and deterministic alphabetic or numeric suffixing.

### Mirror Door

Finds mirrored and unmirrored host-document door instances using the real `FamilyInstance.Mirrored` property. The command supports selected elements, active view, or whole-project scanning, in-model selection, and Excel-compatible CSV export.

### Auto Plan Dimension

Adds automated plan-dimensioning support from the `Dimensions` panel for supported plan-view workflows.

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

## Beginner-safe Git workflow

Use this safe sequence if you are still learning Git:

1. Check current state:
   `git status -sb`
2. Confirm branch and remote:
   `git branch --show-current`
   `git remote -v`
3. Pull safely when working tree is clean:
   `git pull --ff-only`
4. Stage only intended files:
   `git add <file1> <file2>`
5. Commit with a clear message:
   `git commit -m "Short, specific summary"`
6. Push your branch:
   `git push origin <branch-name>`

If files appear that you did not mean to change, stop and review before committing.

## Release Packaging

GitHub Actions validates public release metadata on every push and pull request.

Tagged releases also generate a versioned ZIP package that contains:

- `AEBTools.extension`
- `README.md`
- `CHANGELOG.md`
- `RELEASE_NOTES.md`
- `VERSION`

## Repository Contents

- `AEBTools.extension` - runtime-only pyRevit extension files for installation
- `README.md` - install and usage guide
- `CHANGELOG.md` - public release history
- `RELEASE_NOTES.md` - latest public release summary
- `VERSION` - current public package version

## Support

Use this repository for installation and updates. If a released package has a reproducible issue, open a GitHub issue with the Revit version, pyRevit version, and a short reproduction note.

## GitHub Project Files

This repository includes standard GitHub community files for issues, pull requests, contribution guidance, security reporting, and repository conduct so public maintenance can stay structured as the toolset grows.
