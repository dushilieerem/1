# -*- coding: utf-8 -*-
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8766"


def req(method, path, token=None, body=None):
    data = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode()
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def main():
    for u, p in [("admin", "admin123"), ("maruixiang", "123456"), ("max", "123456")]:
        st, login = req("POST", "/api/auth/login", body={"username": u, "password": p})
        print("login", u, st, "uid=", login.get("user", {}).get("id"))
        tok = login["token"]
        st, me = req("GET", "/api/auth/me", token=tok)
        print("  me", me.get("user", {}).get("id"), me.get("user", {}).get("username"))
        st, proj = req("GET", "/api/detect/projects?visible=1", token=tok)
        names = [(x["name"], x["factorName"], x["id"][:12]) for x in proj.get("projects", [])]
        print("  projects", len(names), names)


if __name__ == "__main__":
    main()
