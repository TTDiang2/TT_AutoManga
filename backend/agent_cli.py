"""Command-line shell over the agent API — one subcommand = one HTTP call.

Environment:
    AUTOMANGA_URL   base URL, default http://127.0.0.1:5180

Examples:
    python -m backend.agent_cli health
    python -m backend.agent_cli new "My Comic"
    python -m backend.agent_cli set-panels <pid> panels.json
    python -m backend.agent_cli gen <pid> panel_1 "1girl, rain" --variants 2
    python -m backend.agent_cli batch jobs.json
    python -m backend.agent_cli job <job_id>
    python -m backend.agent_cli pages <pid> spec.json
    python -m backend.agent_cli preview <pid> <page_id> -o page1.png --scale 2
    python -m backend.agent_cli export <pid> --format both
"""
import argparse
import json
import os
import sys

import httpx

BASE = os.environ.get("AUTOMANGA_URL", "http://127.0.0.1:5180").rstrip("/")


def _request(method: str, path: str, body=None):
    try:
        r = httpx.request(method, BASE + path, json=body, timeout=300.0)
    except httpx.HTTPError as e:
        print(f"error: cannot reach {BASE}: {e}", file=sys.stderr)
        sys.exit(2)
    if r.headers.get("content-type", "").startswith("application/json"):
        data = r.json()
    else:
        data = r.content
    if r.status_code >= 400:
        print(f"HTTP {r.status_code}: {data}", file=sys.stderr)
        sys.exit(1)
    return data


def _print(data):
    if isinstance(data, bytes):
        print(f"<{len(data)} bytes binary>")
        return
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _read_json_file(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    p = argparse.ArgumentParser(prog="automanga",
                                description="TT_AutoManga agent CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health")
    sub.add_parser("projects")

    sp = sub.add_parser("new")
    sp.add_argument("name")

    sp = sub.add_parser("panels")
    sp.add_argument("project_id")

    sp = sub.add_parser("set-panels")
    sp.add_argument("project_id")
    sp.add_argument("json_file", help="JSON file: {\"panels\": [...]}")

    sp = sub.add_parser("gen")
    sp.add_argument("project_id")
    sp.add_argument("panel_id")
    sp.add_argument("prompt")
    sp.add_argument("--no-bg", action="store_true",
                    help="request transparent background (SwarmUI removebackground)")
    sp.add_argument("--seed", type=int)
    sp.add_argument("--variants", type=int, default=1)

    sp = sub.add_parser("batch")
    sp.add_argument("jobs_file",
                    help="JSON file: {\"project_id\": ..., \"concurrency\": 1, \"jobs\": [...]}")

    sub.add_parser("job").add_argument("job_id")

    sp = sub.add_parser("pages")
    sp.add_argument("project_id")
    sp.add_argument("spec_file",
                    help="JSON: {\"template\": {...}, \"panel_ids\": [...], ...}")

    sp = sub.add_parser("element")
    sp.add_argument("project_id")
    sp.add_argument("page_id")
    sp.add_argument("element_file", help="JSON element dict")

    sp = sub.add_parser("preview")
    sp.add_argument("project_id")
    sp.add_argument("page_id")
    sp.add_argument("--scale", type=float, default=2.0)
    sp.add_argument("-o", "--out", default="preview.png")

    sp = sub.add_parser("export")
    sp.add_argument("project_id")
    sp.add_argument("--format", default="both", choices=["pdf", "zip", "both"])
    sp.add_argument("--scale", type=float, default=2.0)

    args = p.parse_args(argv)

    if args.cmd == "health":
        _print(_request("GET", "/api/health"))
    elif args.cmd == "projects":
        _print(_request("GET", "/api/agent/projects"))
    elif args.cmd == "new":
        _print(_request("POST", "/api/agent/projects",
                        {"name": args.name, "panels": []}))
    elif args.cmd == "panels":
        _print(_request("GET", f"/api/agent/projects/{args.project_id}"))
    elif args.cmd == "set-panels":
        body = _read_json_file(args.json_file)
        _print(_request("PUT", f"/api/agent/projects/{args.project_id}/panels", body))
    elif args.cmd == "gen":
        body = {"project_id": args.project_id, "panel_id": args.panel_id,
                "prompt": args.prompt, "remove_background": args.no_bg,
                "variants": args.variants}
        if args.seed is not None:
            body["seed"] = args.seed
        _print(_request("POST", "/api/agent/generate", body))
    elif args.cmd == "batch":
        _print(_request("POST", "/api/agent/generate-batch",
                        _read_json_file(args.jobs_file)))
    elif args.cmd == "job":
        _print(_request("GET", f"/api/agent/jobs/{args.job_id}"))
    elif args.cmd == "pages":
        _print(_request("POST", f"/api/agent/projects/{args.project_id}/pages",
                        _read_json_file(args.spec_file)))
    elif args.cmd == "element":
        _print(_request("POST",
                        f"/api/agent/projects/{args.project_id}/pages/{args.page_id}/elements",
                        _read_json_file(args.element_file)))
    elif args.cmd == "preview":
        data = _request("GET",
                        f"/api/agent/projects/{args.project_id}/pages/{args.page_id}/preview.png"
                        f"?scale={args.scale}")
        with open(args.out, "wb") as f:
            f.write(data)
        print(f"saved {args.out} ({len(data)} bytes)")
    elif args.cmd == "export":
        _print(_request("POST", "/api/agent/export",
                        {"project_id": args.project_id, "format": args.format,
                         "scale": args.scale}))


if __name__ == "__main__":
    main()
