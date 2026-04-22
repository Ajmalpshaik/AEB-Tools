# Mirror Door

## Purpose

Finds placed host-document door instances and identifies whether each instance is mirrored by reading the real `FamilyInstance.Mirrored` property.

## Notes

- Supported scopes are **Selected Elements**, **Active View**, and **Whole Project**.
- Linked-model doors are not processed; only host-document door instances are analyzed.
- The tool now uses one integrated working window that contains scope selection, scan, mirrored and unmirrored lists, and export actions.
- `Export Full Report to Excel` writes an Excel-compatible `.csv` file to avoid external dependencies.
- Grouped mirrored doors are still reported safely.
- `icon.png` is included in this bundle. Editable icon sources should be maintained under `dev/assets/icons/`.
