# Projects

The project module validates the versioned project manifest and exposes fixed format-version-1
paths. It never searches parent directories or creates paths while opening a project.

## Public project namespace

::: persistra.project
    options:
      members: true

## Project errors

Project and manifest failures raise `persistra.errors.ProjectError`.

## Validation diagnostics

::: persistra.validation
    options:
      members: true
