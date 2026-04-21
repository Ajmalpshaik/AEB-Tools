# Room to Door

## Purpose

Writes a user-selected writable text door parameter using:

`Room Number + Separator + Suffix`

Examples:

- `101`
- `101-A`
- `101-B`
- `101-1`
- `101-2`

## Notes

- Default scope is **Whole Project** so existing host-model doors are found even when they are not visible in the current view.
- Linked-model doors are not edited; only host-document door instances are processed.
- Grouped doors are included, but Revit may still block writes when a chosen parameter cannot vary by group member.
- `icon.png` is included in this bundle. The editable source icon is maintained in the private workspace under `dev/assets/icons/room_to_door_source.png`.
- Smoke coverage for this tool is maintained in the private workspace QA documentation.
