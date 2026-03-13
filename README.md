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
export CONFLUENCE_TOKEN_EXPIRES_ON="2026-03-20"   # optional doctor warning
```

Auth behavior:
- If `CONFLUENCE_EMAIL` is set, CLI uses Basic auth (`email:token`) for Atlassian Cloud.
- If email is not set, CLI falls back to Bearer token auth.

Token reminder:
- Current working token was created on `2026-03-13` and is set to expire on `2026-03-20` (one week).
- Rotate the token before expiry to avoid export failures.

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
bin/confluence-workflow.sh export-space IN
bin/confluence-workflow.sh export-cql "space=IN and type=page and label=network"
bin/confluence-workflow.sh build-contents
```

- `doctor` writes a timestamped diagnostics log in `tmp/`
- `doctor` also runs a Confluence health probe and warns if token is near expiry
- `health` checks API access with current env vars
- `export-page` exports JSON to `exports/` (or custom output path)
- `export-space` writes batch JSON + `pages.jsonl` for AI
- `export-cql` runs batch export against custom CQL filters
- `build-contents` creates a hierarchical markdown contents page (`exports/contents.md`)

## Batch Export

Direct CLI examples:

```bash
confluence-export export-batch --space-key IN --output exports
confluence-export export-batch --cql "space=IN and type=page" --output exports --max-pages 200
confluence-export build-contents --input-pages-dir exports/pages --output exports/contents.md
```

Batch output:
- `exports/pages/*.json` raw page JSON snapshots
- `exports/pages.jsonl` one record per page (`id`, `title`, `space_key`, `content`)
- `exports/manifest.json` export index and error summary
- `exports/contents.md` quality table-of-contents style navigation page

## Feeding Into AI (Recommended)

Use `pages.jsonl` as the primary AI input because it is line-delimited, chunkable, and easy to index.

Typical pipeline:
1. Export content (`export-space` or `export-cql`)
2. Split large page bodies into chunks (by heading/size)
3. Embed and index chunks in your vector store
4. Use retrieval + summarization to answer questions with citations

## Deliverables (Recommended)

1. **AI Wiki Assistant (primary)**
	- Uses `pages.jsonl` + retrieval for cited Q&A over Confluence content.
2. **Quality Contents Page (navigation)**
	- Uses `build-contents` output as a human-readable entry point into exported docs.
3. **Executive Report (secondary)**
	- Periodic summary of key updates, risks, and actions generated from exported pages.

If you want “a wiki-like AI,” prioritize the AI assistant + contents page first, then layer in executive reporting.
