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
        assert st == 200, login
        tok = login["token"]
        st, proj = req("GET", "/api/detect/projects?visible=1", token=tok)
        assert st == 200, proj
        sample = next(x for x in proj["projects"] if x["id"] == "sample_momentum_5d")
        st, runs = req("GET", "/api/detect/projects/sample_momentum_5d/runs", token=tok)
        assert st == 200, runs
        desc = runs["runs"][0]["description"] if runs["runs"] else "-"
        print(f"{u}: runCount={sample['runCount']} runs={len(runs['runs'])} desc={desc}")

    st, m = req("POST", "/api/auth/login", body={"username": "maruixiang", "password": "123456"})
    st, x = req("POST", "/api/auth/login", body={"username": "max", "password": "123456"})
    st, mruns = req("GET", "/api/detect/projects/sample_momentum_5d/runs", token=m["token"])
    rid = mruns["runs"][0]["id"]
    st, _ = req("GET", f"/api/detect/runs/{rid}", token=x["token"])
    print("cross-read status", st, "(expect 404)")
    assert st == 404
    st, _ = req("GET", "/api/detect/projects")
    print("unauth status", st, "(expect 401)")
    assert st == 401
    print("ALL HTTP CHECKS OK")


if __name__ == "__main__":
    main()
