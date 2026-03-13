# Confluence Export CLI

CLI tool for exporting Confluence content for downstream AI analysis and summarization.

## Planned Capabilities
- Export page content by page ID
- Export metadata for auditing
- Batch export by CQL query / space key
- Persist exports as JSON/Markdown for AI pipelines

## Setup
1. Create and activate a Python virtual environment.
2. Install the package in editable mode:

```bash
pip install -e .
```

3. Set environment variables:

```bash
export CONFLUENCE_BASE_URL="https://<your-domain>.atlassian.net/wiki"
export CONFLUENCE_API_TOKEN="<api-token>"
export CONFLUENCE_EMAIL="<your-email>"   # recommended for Atlassian Cloud
```

Auth behavior:
- If `CONFLUENCE_EMAIL` is set, CLI uses Basic auth (`email:token`) for Atlassian Cloud.
- If email is not set, CLI falls back to Bearer token auth.

4. Run:

```bash
confluence-export health
```

## Example

```bash
confluence-export export-page --page-id 123456 --output exports/
```

## Trackpad-Saver Shortcuts

Use the helper script for repetitive tasks:

```bash
bin/confluence-workflow.sh doctor
bin/confluence-workflow.sh health
bin/confluence-workflow.sh export-page 123456
```

- `doctor` writes a timestamped diagnostics log in `tmp/`
- `health` checks API access with current env vars
- `export-page` exports JSON to `exports/` (or custom output path)
