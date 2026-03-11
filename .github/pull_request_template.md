<!--
PR Title Format: <type>(<scope>): <description>

Examples:
  feat(pipeline): add H.265 codec support
  fix(upload): resolve large file timeout
  docs(readme): update installation steps
  refactor(pipeline): consolidate chunk processing
  test(pipeline): add upscale integration tests

Types: feat, fix, docs, refactor, test, chore, style, perf
Scope: Component/feature area (pipeline, upload, preview, ui, etc.)
Description: Imperative mood, concise (50 chars or less)
-->

## What Changed

<!-- Brief summary of the changes in this PR -->

## Why This Change

<!-- Motivation and context - what problem does this solve? -->

## How It Works

<!-- Implementation approach (required for refactors, feature changes, architectural modifications, behavior changes; optional for docs/test-only updates) -->

## Testing Done

<!-- How did you verify these changes work? -->

- [ ] Application starts (`start.bat`)
- [ ] Upload works (drag-and-drop or file path)
- [ ] Preview generates correctly
- [ ] Upscale processes without errors
- [ ] Manual testing completed

## Screenshots/Videos

<!-- If UI changes, add screenshots or screen recordings -->

## Related Issues/PRs

<!-- Link to related issues or PRs -->

Closes # Related to #

## Pre-Merge Checklist

- [ ] Application runs without errors
- [ ] Pipeline handles large files correctly
- [ ] No security regressions (path traversal, subprocess safety)
- [ ] Breaking changes documented (if any)
- [ ] Documentation updated (if needed)
