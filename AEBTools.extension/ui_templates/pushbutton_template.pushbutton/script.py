"""
Tool Name    : Pushbutton Template Script
Purpose      : Provide a starter pyRevit pushbutton command for template-based tool creation
Author       : Ajmal P.S.
Company      : AJ Tools
Version      : 1.0.0
Created      : 2026-04-21
Last Updated : 2026-04-21
Target       : Revit 2020-2027
Platform     : pyRevit / Python
Dependencies : pyRevit
Input        : Active pyRevit session
Output       : Template command log output and confirmation text
Notes        : Serves as the default starter script for new pushbutton-based tools
Changelog    : v1.0.0 - Added standardized metadata header
License      : All Rights Reserved
Repo         : AEB-Tools
"""

from pyrevit import script


def main():
    logger = script.get_logger()
    output = script.get_output()
    logger.info("Smoke-test pushbutton executed.")
    output.print_md("## Smoke Test\\nPushbutton template executed successfully.")


if __name__ == "__main__":
    main()
