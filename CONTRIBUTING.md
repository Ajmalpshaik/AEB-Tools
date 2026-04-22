# Contributing

## Repository Purpose

This is the public install repository for `AEB Tools`. It is primarily used to:

- distribute stable pyRevit extension files
- publish tagged release packages
- track public issues for released builds

Core development, internal testing, and source workspace automation are maintained separately.

## What To Open Here

Open a GitHub issue in this repository when you have:

- a reproducible bug in a released package
- an installation problem with this public repository
- a request for a small public-facing repository improvement

## Before Opening An Issue

Please include the practical details needed to investigate the problem:

- Revit version
- pyRevit version
- AEB Tools release version
- whether the model is local, central, or linked-dependent
- a short reproduction sequence
- screenshots or error text if available

## Pull Requests

Pull requests are welcome for repository-facing improvements such as:

- documentation fixes
- GitHub workflow fixes
- issue template improvements
- release automation corrections

Do not use this repository for large feature development or partial internal source drops unless that work is intentionally meant for the public install repo.

## Pull Request Expectations

Before opening a pull request:

1. Keep the scope focused.
2. Update documentation if behavior or release flow changes.
3. Run the relevant local checks when possible.
4. Make sure new GitHub workflow or release changes are coherent with the public install purpose of this repository.

## Release Metadata

If a change modifies public release packaging or package metadata:

- keep `VERSION` aligned with the intended tagged release
- update `CHANGELOG.md`
- update `RELEASE_NOTES.md`
- keep bundle metadata aligned with the public version

## Support Boundary

If your request is actually about internal tool design, enterprise customization, or private workspace development, this repository is not the right place to submit implementation details. Use the public repo only for the public install package and its GitHub-facing maintenance.
