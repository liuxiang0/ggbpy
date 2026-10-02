#!/usr/bin/env python3
"""多会话隔离检测（P2）：cookie/?sid= 解析、构造/撤销/state3d rev/宏 的会话隔离、上限与 TTL。

用法：
    python3 -B devtools/test_sessions.py [--base http://127.0.0.1:8090]
退出码：0 通过 / 1 失败 / 2 服务不可用
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8090"
if "--base" in sys.argv:
    BASE = sys.argv[sys.argv.index("--base") + 1]

PASS = 0
FAIL = 0
FAILED = []


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  OK   " + name + (("  [" + detail + "]") if detail else ""))
    else:
        FAIL += 1
        FAILED.append(name)
        print("  FAIL " + name + "  " + detail)


def req(path, body=None, method=None, headers=None):
    hdr = {"Content-Type": "application/json"}
    if headers:
        hdr.update(headers)
    data = None
    if body is not None:
        data = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
    r = urllib.request.Request(BASE + path, data=data, headers=hdr,
                               method=method or ("POST" if data else "GET"))
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read()
            try:
                js = json.loads(raw.decode("utf-8"))
            except Exception:
                js = None
            return resp.status, dict(resp.headers), raw, js
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            js = json.loads(raw.decode("utf-8"))
        except Exception:
            js = None
        return e.code, dict(e.headers or {}), raw, js
    except Exception as e:
        return 0, {}, str(e).encode(), None


def post(path, body=None):
    st, _h, _raw, js = req(path, body if body is not None else {})
    return st, js or {}


def get(path):
    return req(path)


def sid_q(sid):
    return ("?sid=" + sid) if sid else ""


def inputs(sid, text):
    st, js = post("/api/input" + sid_q(sid), {"text": text})
    return js.get("message", "")


def labels(sid):
    _st, _h, _raw, js = get("/api/state" + sid_q(sid))
    return sorted(e.get("label") for e in (js or {}).get("elements", []))


def hget(headers, name, default=""):
    for k, v in (headers or {}).items():
        if k.lower() == name.lower():
            return v
    return default


print("=== A. 服务与 cookie 探针 ===")
st, h, _raw, _js = get("/api/state")
check("服务可达 " + BASE, st == 200, "HTTP %s" % st)
if st != 200:
    print("\n服务不可用：请先启动（cd ggbpy && PORT=8090 ./run.sh）")
    sys.exit(2)
check("无 cookie 请求保持 cookie-less（落到 default，供脚本使用）",
      "ggbpy_sid=" not in hget(h, "set-cookie"), hget(h, "set-cookie")[:40])
_st_c, h_c, _raw_c, _js_c = get("/api/state?sid=pinned")
check("显式 ?sid= 会下发对应 cookie",
      "ggbpy_sid=pinned" in hget(h_c, "set-cookie"), hget(h_c, "set-cookie")[:50])
check("无 sid 参数时落到 default 会话",
      get("/api/session")[3]["session"]["sid"] == "default",
      str(get("/api/session")[3]["session"]["sid"]))

print("\n=== B. 构造隔离 ===")
for s in ("sessA", "sessB", None):
    post("/api/clear" + sid_q(s), {})
check("A 创建对象不影响 B", inputs("sessA", "A1=(1,1)").startswith("OK")
      and labels("sessA") == ["A1"] and labels("sessB") == [],
      "A=%s B=%s" % (labels("sessA"), labels("sessB")))
inputs("sessB", "B1=(2,2)")
check("B 创建对象不影响 A", labels("sessA") == ["A1"] and labels("sessB") == ["B1"],
      "A=%s B=%s" % (labels("sessA"), labels("sessB")))
inputs(None, "D1=(3,3)")
check("default 会话与命名会话互不影响", labels(None) == ["D1"],
      "default=%s" % labels(None))
check("同一 sid 跨请求保持同一构造",
      labels("sessA") == ["A1"] and labels("sessA") == ["A1"], str(labels("sessA")))

print("\n=== C. 撤销/清空隔离 ===")
_st, j = post("/api/undo" + sid_q("sessA"), {})
check("A 撤销只影响 A（B 仍有对象）",
      labels("sessA") == [] and labels("sessB") == ["B1"],
      "A=%s B=%s" % (labels("sessA"), labels("sessB")))
post("/api/clear" + sid_q("sessB"), {})
check("A 清空只影响 A", labels("sessB") == [] and labels(None) == ["D1"],
      "B=%s default=%s" % (labels("sessB"), labels(None)))

print("\n=== D. state3d rev 与会话独立 ===")
inputs("sessA", "cu=Cube[(0,0,0),(2,0,0)]")
_st, _h, _raw, sa = get("/api/state3d" + sid_q("sessA"))
_st, _h, _raw, sb = get("/api/state3d" + sid_q("sessB"))
check("A 的 3D 状态含立方体、B 为空",
      len(sa.get("elements", [])) == 1 and len(sb.get("elements", [])) == 0,
      "A=%d B=%d" % (len(sa.get("elements", [])), len(sb.get("elements", []))))
revA = sa.get("rev")
_st, _h, _raw, sa2 = get("/api/state3d%s&since=%d" % (sid_q("sessA"), revA))
check("A 未变更时返回 unchanged", sa2.get("unchanged") is True and sa2.get("rev") == revA,
      str(sa2)[:60])
inputs("sessB", "cuB=Cube[(0,0,0),(1,0,0)]")
_st, _h, _raw, sb2 = get("/api/state3d" + sid_q("sessB"))
check("B 的 rev 独立于 A", sb2.get("rev") != revA or len(sb2.get("elements", [])) == 1,
      "revA=%s revB=%s" % (revA, sb2.get("rev")))

print("\n=== E. 宏隔离 ===")
for s in ("m1", "m2"):
    post("/api/clear" + sid_q(s), {})
for ln in ("A=(0,0)", "B=(2,0)", "C=(0,2)", "tri=Polygon[A,B,C]"):
    inputs("m1", ln)
_st, jc = post("/api/macro/create" + sid_q("m1"), {"name": "tri3", "inputs": ["A", "B", "C"],
                                                   "outputs": ["tri"]})
names1 = [m.get("name") for m in (get("/api/macro" + sid_q("m1"))[3] or {}).get("macros", [])]
names2 = [m.get("name") for m in (get("/api/macro" + sid_q("m2"))[3] or {}).get("macros", [])]
check("A 创建宏后仅 A 可见", "tri3" in names1 and "tri3" not in names2,
      "A=%s B=%s" % (names1, names2))
inputs("m2", "P1=(0,0)")
inputs("m2", "P2=(1,0)")
inputs("m2", "P3=(0,1)")
msg_run_b = inputs("m2", "mm=tri3[P1,P2,P3]")
check("B 运行 A 的宏 → 未知命令", not msg_run_b.startswith("OK"), msg_run_b[:40])

print("\n=== F. 导出/保存按会话 ===")
_st, _h, rawA = get("/api/export/ggb" + sid_q("sessA"))[0:3]
_st, _h, rawB = get("/api/export/ggb" + sid_q("sessB"))[0:3]
check("A 的 .ggb 含 A 的对象（cu）、不含 B 的（cuB）",
      b'label="cu"' in rawA and b'label="cuB"' not in rawA,
      "len=%d" % len(rawA))
check("B 的 .ggb 含 B 的对象（cuB）", b'label="cuB"' in rawB, "len=%d" % len(rawB))
_st, _h, rawG = get("/api/download" + sid_q("sessB"))[0:3]
check("B 的 .ggk 含 B 的对象", b'"cuB"' in rawG or b"cuB" in rawG, "len=%d" % len(rawG))

print("\n=== G. 会话信息与清理 ===")
_st, _h, _raw, info = get("/api/session" + sid_q("sessA"))
check("/api/session 返回当前会话与概览",
      info["session"]["sid"] == "sessA" and info["sessions"]["count"] >= 3,
      "sid=%s count=%s" % (info["session"]["sid"], info["sessions"]["count"]))
_st, sw = post("/api/session/sweep", {})
check("/api/session/sweep 可调用", sw.get("ok") is True and "dropped" in sw, str(sw)[:60])

print("\n=== H. 会话上限 / TTL（单元级） ===")
sys.path.insert(0, ".")
import server.sessions as S  # noqa: E402

S.reset_for_tests()
_old_max, _old_ttl = S.MAX_SESSIONS, S.TTL_SECONDS
S.MAX_SESSIONS = 3
for i in range(6):
    S.get_session("cap%d" % i)
check("会话数不超过上限（淘汰最久未用）", len(S.session_stats()["sids"]) <= 3 + 1,
      "count=%s" % len(S.session_stats()["sids"]))
S.get_session(S.DEFAULT_SID)
check("default 会话存在且不被淘汰", any(s["sid"] == S.DEFAULT_SID for s in S.session_stats()["sids"]))
S.TTL_SECONDS = 0
time.sleep(0.01)
dropped = S.sweep()
left = {s["sid"] for s in S.session_stats()["sids"]}
check("TTL 过期会话被清理，default 保留", dropped >= 1 and left == {S.DEFAULT_SID},
      "dropped=%d left=%s" % (dropped, left))
S.MAX_SESSIONS, S.TTL_SECONDS = _old_max, _old_ttl
S.reset_for_tests()

print("\n" + "=" * 60)
print("会话隔离检测：%d 项断言，%d 失败" % (PASS + FAIL, FAIL))
if FAILED:
    for n in FAILED:
        print("  FAILED: " + n)
    print("结果: FAILED")
    sys.exit(1)
print("结果: ALL PASS")
sys.exit(0)
