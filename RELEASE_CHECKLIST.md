# Release Checklist (Python SDK)

## Pre-check
- [ ] Confirm branch is `main` and working tree clean
- [ ] Version in `pyproject.toml` updated if release build

## Quality gate
- [ ] `python -m pytest -q`
- [ ] Validate API compatibility with latest backend:
  - [ ] conversation `public_id`
  - [ ] message extended fields (reply/reactions/mentions)
  - [ ] entity ops (`self-check`, `diagnostics`, `regenerate-token`)

## Package
- [ ] `python -m build`
- [ ] Inspect wheel metadata and import path compatibility (`agent_im_python`, `agent_native_im_sdk_python`)

## Publish
- [ ] Tag release
- [ ] Upload package to registry (if enabled)

## Post-check
- [ ] Install from built artifact in clean venv
- [ ] Run quick bot example
