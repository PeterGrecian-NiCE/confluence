import json
import os
import base64
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
    url = f"{base_url}/rest/api/content/{page_id}"
    params = {"expand": "body.storage,version,space"}
    response = client.get(url, params=params)
    response.raise_for_status()

    payload = response.json()
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"page-{page_id}.json"
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    typer.echo(str(out_file))


if __name__ == "__main__":
    app()
