#!/usr/bin/env python3
"""Send one authorized request to the existing institutional-quant relay; never resume a session."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
TARGET = "张新迪-机构侧量化平台-联络"
TARGET_CWD = "/home/dev01/project/SVQuant-zxd"
TARGET_SESSION_ID = "afcf6e55-988c-4724-9f3c-078b3f81708b"

def timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def write_private(path, value):
    with path.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    path.chmod(0o600)

def decode_result(content):
    if isinstance(content, str):
        try:
            return [json.loads(content)]
        except ValueError:
            return []
    results = []
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                results.extend(decode_result(part["text"]))
    return results

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request_id")
    parser.add_argument("--check", action="store_true", help="Validate request and target without sending or calling the model")
    args = parser.parse_args()
    if not re.fullmatch(r"CX-\d{8}-\d{3}", args.request_id):
        parser.error("Expected CX-YYYYMMDD-NNN")
    request = ROOT / "requests" / (args.request_id + ".md")
    if not request.is_file() or request.is_symlink():
        parser.error("Request must be an existing regular file in requests/")
    inventory = subprocess.run(
        ["claude", "agents", "--json"], capture_output=True, text=True,
        encoding="utf-8", timeout=20, check=True)
    rows = json.loads(inventory.stdout)
    if not isinstance(rows, list):
        raise RuntimeError("Unexpected agents inventory format")
    candidates = [row for row in rows if row.get("name") == TARGET and row.get("cwd") == TARGET_CWD and row.get("sessionId") == TARGET_SESSION_ID]
    if len(candidates) != 1 or sum(row.get("name") == TARGET for row in rows) != 1:
        raise RuntimeError("Expected one unambiguous live relay with the configured name, directory, and session ID")
    if args.check:
        print(json.dumps({"request_id": args.request_id, "target": TARGET, "target_status": candidates[0].get("status"), "target_session_id": TARGET_SESSION_ID, "action": "checked_only_no_message"}, ensure_ascii=False))
        return 0

    transport = ROOT / "transport"
    transport.mkdir(mode=0o700, exist_ok=True)
    status_path = transport / (args.request_id + ".status.json")
    # The exclusive marker survives failures: uncertain sends are never automatically retried.
    status = {"request_id": args.request_id, "target": TARGET, "target_session_id": TARGET_SESSION_ID, "state": "started", "started_at": timestamp()}
    try:
        fd = os.open(status_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise RuntimeError("A previous send attempt exists. Inspect its trace and reply; do not resend blindly.")
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(status, stream, ensure_ascii=False)
    if (ROOT / "responses" / (args.request_id + ".md")).exists():
        status.update(state="not_sent_reply_already_exists", finished_at=timestamp())
        write_private(status_path, status)
        raise RuntimeError("A reply already exists; refusing duplicate notification")

    message = (
        f"[{args.request_id} / Codex 经用户授权的联络请求] "
        f"请读取 {request}，按联络台 README.md 的约定处理，"
        f"并把实际发送状态及收到的回复写入 {ROOT / 'responses' / (args.request_id + '.md')}。"
        "请先按请求编号检查已有处理记录，避免重复转发。只执行请求明确授权的联络范围，遵守你现有权限。"
    )
    prompt = (
        "You are a one-shot native message transport for Codex, authorized by the user to contact their existing relay session. "
        f"Use ListAgents to locate exactly {TARGET} with session ID {TARGET_SESSION_ID} in {TARGET_CWD}; use the exact disambiguated target returned by ListAgents. "
        "Do not contact 张新迪-数据需求, historical 张新迪 sessions, or svquant-zxd-ec. "
        "If the target is missing or ambiguous, report failure. Send the following message verbatim exactly once via SendMessage. "
        "Do not contact other sessions, resume any session, spawn workers, alter configuration, or perform development. "
        "Report the native delivery result and exit; the receiver replies via the file, not to this short-lived process.\n" + message
    )
    command = [
        "claude", "--safe-mode", "--print", "--name", "codex-relay-" + args.request_id.lower(),
        "--tools", "ListAgents,SendMessage", "--allowedTools", "ListAgents,SendMessage",
        "--permission-mode", "dontAsk", "--no-session-persistence",
        "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
        "--effort", "low", "--max-budget-usd", "0.25",
        "--output-format", "stream-json", "--verbose", prompt,
    ]
    output_path = transport / (args.request_id + ".stdout.jsonl")
    error_path = transport / (args.request_id + ".stderr.txt")
    timed_out = False
    try:
        with output_path.open("x", encoding="utf-8") as out, error_path.open("x", encoding="utf-8") as err:
            output_path.chmod(0o600)
            error_path.chmod(0o600)
            process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
            status["process_id"] = process.pid
            write_private(status_path, status)
            try:
                returncode = process.wait(timeout=90)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.terminate()
                try:
                    returncode = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    returncode = process.wait()
        messages = []
        for line in output_path.read_text(encoding="utf-8").splitlines():
            try:
                messages.append(json.loads(line))
            except ValueError:
                pass
        sends, tool_results, run_result = [], {}, {}
        for entry in messages:
            if entry.get("type") == "result":
                run_result = entry
            parts = entry.get("message", {}).get("content", [])
            if not isinstance(parts, list):
                continue
            for part in parts:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "tool_use" and part.get("name") == "SendMessage":
                    sends.append(part)
                if part.get("type") == "tool_result":
                    tool_results[part.get("tool_use_id")] = decode_result(part.get("content"))
        queued = False
        msg_id = None
        if len(sends) == 1:
            send = sends[0]
            arguments = send.get("input", {})
            recipient = arguments.get("to", arguments.get("recipient"))
            body = arguments.get("message", arguments.get("content", ""))
            # Native output, not the model's final sentence, is the transport evidence.
            target_matches = recipient in {TARGET, f"{TARGET} [{TARGET_SESSION_ID[:8]}]", f"{TARGET} [{TARGET_SESSION_ID}]"}
            if target_matches and str(request) in body:
                for result in tool_results.get(send.get("id"), []):
                    if isinstance(result, dict) and result.get("success") is True:
                        queued = True
                        msg_id = result.get("msg_id")
        state = "queued_reply_not_verified" if queued else "not_confirmed_no_automatic_retry"
        status.update(
            state=state, finished_at=timestamp(), native_message_id=msg_id,
            process_exit=returncode, timed_out=timed_out, send_calls=len(sends),
            reported_cost_usd=run_result.get("total_cost_usd"),
            reply_file_exists=(ROOT / "responses" / (args.request_id + ".md")).is_file())
        write_private(status_path, status)
        print(json.dumps(status, ensure_ascii=False))
        return 0 if queued else 2
    except Exception as exc:
        status.update(state="error_delivery_unknown_no_automatic_retry", finished_at=timestamp(), error_type=type(exc).__name__)
        write_private(status_path, status)
        raise

if __name__ == "__main__":
    sys.exit(main())
