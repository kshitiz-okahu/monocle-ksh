## Prepare Release Branch Workflow

This GitHub Actions workflow automates the preparation of a release branch. It is triggered manually via `workflow_dispatch` with a required input for the pre-release version number.

### Workflow Steps

1. **Prerequisites Check**:
   - Verifies that the workflow is run against the `main` branch.
   - Checks for the presence of an "Unreleased" section in the `CHANGELOG.md`.
   - Validates the pre-release version number.

2. **Create Pull Request Against Release Branch**:
   - Creates a new release branch based on the stable version.
   - Updates the changelog with the approximate release date.
   - Creates a new pre release branch
   - Creates a pull request against the release branch.

3. **Create Pull Request Against Main**:
   - Sets environment variables for stable version.
   - Updates the changelog on the `main` branch with the release date.
   - Creates a pull request against the `main` branch to update the version.

### Scripts Used

- **eachdist.py**:
  - This script is used to manage versioning for the project.
  - It has two modes:
    - `--mode stable`: Retrieves the stable version of the project.
  - The script is executed with the necessary permissions using `chmod +x`.

- **CHANGELOG.md**:
  - The changelog file is updated to reflect the new release version and date.
  - The script uses `sed` to replace the "Unreleased" section with the new version and date.

### Troubleshooting

- If the creation of branch fails due to permission, check the permission for github applications.
