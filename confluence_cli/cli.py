import json
import os
import base64
import re
from pathlib import Path

import httpx
import typer
from dotenv import load_dotenv


load_dotenv()
app = typer.Typer(no_args_is_help=True)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise typer.BadParameter(f"Missing required environment variable: {name}")
    return value


def _first_set(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _auth_headers() -> dict[str, str]:
    token = _first_set("CONFLUENCE_API_TOKEN", "ATLASSIAN_API_TOKEN", "CONFLUENCE_TOKEN")
    if not token:
        raise typer.BadParameter(
            "Missing API token. Set one of: CONFLUENCE_API_TOKEN, ATLASSIAN_API_TOKEN, CONFLUENCE_TOKEN"
        )

    email = _first_set("CONFLUENCE_EMAIL", "ATLASSIAN_EMAIL", "ATLASSIAN_USER_EMAIL")

    if email:
        basic = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
        return {
            "Authorization": f"Basic {basic}",
            "Accept": "application/json",
        }

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def _confluence_client() -> tuple[str, httpx.Client]:
    base_url = _required_env("CONFLUENCE_BASE_URL").rstrip("/")
    headers = _auth_headers()
    client = httpx.Client(headers=headers, timeout=30)
    return base_url, client


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return cleaned or "untitled"


def _fetch_page(base_url: str, client: httpx.Client, page_id: str) -> dict:
    url = f"{base_url}/rest/api/content/{page_id}"
    params = {"expand": "body.storage,version,space,ancestors"}
    response = client.get(url, params=params)
    response.raise_for_status()
    return response.json()


def _content_url(base_url: str, page_payload: dict) -> str:
    links = page_payload.get("_links") or {}
    webui = str(links.get("webui", "")).strip()
    if webui:
        if webui.startswith("http://") or webui.startswith("https://"):
            return webui
        return f"{base_url.rstrip('/')}{webui}"

    page_id = str(page_payload.get("id", "")).strip()
    return f"{base_url.rstrip('/')}/pages/viewpage.action?pageId={page_id}"


@app.command("health")
def health() -> None:
    base_url, client = _confluence_client()
    url = f"{base_url}/rest/api/space?limit=1"
    response = client.get(url)
    response.raise_for_status()
    typer.echo("ok")


@app.command("export-page")
def export_page(
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID"),
    output: str = typer.Option("exports", "--output", help="Output directory"),
) -> None:
    base_url, client = _confluence_client()
    payload = _fetch_page(base_url=base_url, client=client, page_id=page_id)
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"page-{page_id}.json"
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    typer.echo(str(out_file))


@app.command("export-batch")
def export_batch(
    output: str = typer.Option("exports", "--output", help="Output directory"),
    space_key: str = typer.Option(
        "",
        "--space-key",
        help="Export all pages from this Confluence space key",
    ),
    cql: str = typer.Option(
        "",
        "--cql",
        help="Custom CQL query (overrides --space-key when provided)",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        min=1,
        max=100,
        help="Search page size (max 100)",
    ),
    max_pages: int = typer.Option(
        0,
        "--max-pages",
        min=0,
        help="Maximum number of pages to export (0 means all)",
    ),
    jsonl: bool = typer.Option(
        True,
        "--jsonl/--no-jsonl",
        help="Write AI-friendly pages.jsonl output",
    ),
) -> None:
    query = cql.strip()
    if not query:
        if not space_key.strip():
            raise typer.BadParameter("Provide either --space-key or --cql")
        query = f'space="{space_key.strip()}" and type=page'

    base_url, client = _confluence_client()

    out_dir = Path(output)
    pages_dir = out_dir / "pages"
    out_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "query": query,
        "limit": limit,
        "max_pages": max_pages,
        "exported": [],
        "errors": [],
    }

    start = 0
    exported_count = 0
    jsonl_path = out_dir / "pages.jsonl"
    jsonl_handle = jsonl_path.open("w", encoding="utf-8") if jsonl else None

    try:
        while True:
            search_url = f"{base_url}/rest/api/content/search"
            params = {
                "cql": query,
                "start": start,
                "limit": limit,
            }
            response = client.get(search_url, params=params)
            response.raise_for_status()
            payload = response.json()

            results = payload.get("results", [])
            if not results:
                break

            for item in results:
                page_id = str(item.get("id", "")).strip()
                if not page_id:
                    continue

                try:
                    page_payload = _fetch_page(base_url=base_url, client=client, page_id=page_id)
                    title = str(page_payload.get("title", "untitled"))
                    safe_title = _safe_name(title)[:80]
                    page_file = pages_dir / f"{page_id}-{safe_title}.json"
                    page_file.write_text(json.dumps(page_payload, indent=2), encoding="utf-8")

                    page_entry = {
                        "id": page_id,
                        "title": title,
                        "space_key": ((page_payload.get("space") or {}).get("key")),
                        "version": ((page_payload.get("version") or {}).get("number")),
                        "file": str(page_file),
                    }
                    manifest["exported"].append(page_entry)
                    exported_count += 1

                    if jsonl_handle:
                        body_storage = ((page_payload.get("body") or {}).get("storage") or {})
                        jsonl_record = {
                            "id": page_id,
                            "title": title,
                            "space_key": page_entry["space_key"],
                            "version": page_entry["version"],
                            "content_format": body_storage.get("representation"),
                            "content": body_storage.get("value", ""),
                        }
                        jsonl_handle.write(json.dumps(jsonl_record, ensure_ascii=False) + "\n")

                except httpx.HTTPStatusError as exc:
                    manifest["errors"].append(
                        {
                            "id": page_id,
                            "status": exc.response.status_code if exc.response else None,
                            "error": str(exc),
                        }
                    )
                except Exception as exc:
                    manifest["errors"].append(
                        {
                            "id": page_id,
                            "error": str(exc),
                        }
                    )

                if max_pages and exported_count >= max_pages:
                    break

            if max_pages and exported_count >= max_pages:
                break

            start += len(results)
            typer.echo(f"progress: exported={exported_count} scanned={start}")
    finally:
        if jsonl_handle:
            jsonl_handle.close()

    manifest["exported_count"] = len(manifest["exported"])
    manifest["error_count"] = len(manifest["errors"])

    manifest_file = out_dir / "manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    typer.echo(str(manifest_file))
    if jsonl:
        typer.echo(str(jsonl_path))
    typer.echo(f"done: exported={manifest['exported_count']} errors={manifest['error_count']}")


@app.command("build-contents")
def build_contents(
    input_pages_dir: str = typer.Option(
        "exports/pages",
        "--input-pages-dir",
        help="Directory containing exported page JSON files",
    ),
    output: str = typer.Option(
        "exports/contents.md",
        "--output",
        help="Output markdown file path",
    ),
    title: str = typer.Option(
        "Confluence Contents",
        "--title",
        help="Heading title for the generated contents page",
    ),
    base_url: str = typer.Option(
        "",
        "--base-url",
        help="Confluence base URL override (defaults to CONFLUENCE_BASE_URL env)",
    ),
) -> None:
    pages_dir = Path(input_pages_dir)
    if not pages_dir.exists() or not pages_dir.is_dir():
        raise typer.BadParameter(f"Input pages directory not found: {pages_dir}")

    page_files = sorted(pages_dir.glob("*.json"))
    if not page_files:
        raise typer.BadParameter(f"No page JSON files found in: {pages_dir}")

    resolved_base_url = base_url.strip() or os.getenv("CONFLUENCE_BASE_URL", "").strip()

    pages: dict[str, dict] = {}
    for file_path in page_files:
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        page_id = str(payload.get("id", "")).strip()
        if not page_id:
            continue

        ancestors = payload.get("ancestors") or []
        parent_id = ""
        if ancestors:
            parent_id = str((ancestors[-1] or {}).get("id", "")).strip()

        pages[page_id] = {
            "id": page_id,
            "title": str(payload.get("title", "untitled")),
            "space_key": str((payload.get("space") or {}).get("key", "UNKNOWN")),
            "version": (payload.get("version") or {}).get("number"),
            "parent_id": parent_id,
            "url": _content_url(resolved_base_url, payload) if resolved_base_url else "",
        }

    if not pages:
        raise typer.BadParameter(f"No valid pages could be loaded from: {pages_dir}")

    spaces: dict[str, list[str]] = {}
    for page_id, page in pages.items():
        spaces.setdefault(page["space_key"], []).append(page_id)

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- Total pages: {len(pages)}")
    lines.append(f"- Spaces: {len(spaces)}")
    lines.append("")

    for space_key in sorted(spaces.keys()):
        ids_in_space = spaces[space_key]
        id_set = set(ids_in_space)

        children: dict[str, list[str]] = {}
        for pid in ids_in_space:
            page = pages[pid]
            parent_id = page.get("parent_id", "")
            bucket = parent_id if parent_id in id_set else ""
            children.setdefault(bucket, []).append(pid)

        for key in list(children.keys()):
            children[key].sort(key=lambda x: pages[x]["title"].lower())

        lines.append(f"## Space {space_key}")
        lines.append("")

        visited: set[str] = set()

        def emit(page_id: str, depth: int) -> None:
            if page_id in visited:
                return
            visited.add(page_id)
            page = pages[page_id]

            indent = "  " * depth
            title_text = page["title"]
            if page["url"]:
                line = f"{indent}- [{title_text}]({page['url']})"
            else:
                line = f"{indent}- {title_text}"

            meta = f"id={page['id']}"
            if page.get("version") is not None:
                meta += f", v={page['version']}"
            line += f" (`{meta}`)"

            lines.append(line)

            for child_id in children.get(page_id, []):
                emit(child_id, depth + 1)

        for root_id in children.get("", []):
            emit(root_id, 0)

        leftovers = [pid for pid in ids_in_space if pid not in visited]
        if leftovers:
            lines.append("")
            lines.append("### Unlinked Pages")
            lines.append("")
            for pid in sorted(leftovers, key=lambda x: pages[x]["title"].lower()):
                page = pages[pid]
                if page["url"]:
                    lines.append(f"- [{page['title']}]({page['url']}) (`id={page['id']}`)")
                else:
                    lines.append(f"- {page['title']} (`id={page['id']}`)")

        lines.append("")

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    typer.echo(str(output_path))


if __name__ == "__main__":
    app()
