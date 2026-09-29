
import json, urllib.request
BASE = "http://127.0.0.1:8090"
def post(path, obj=None):
    data = json.dumps(obj or {}).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type":"application/json"})
    return urllib.request.urlopen(req).read().decode()
def get(path):
    return urllib.request.urlopen(BASE + path).read().decode()
post("/api/clear")
print("after clear state3d:", get("/api/state3d")[:120])
print("input (1,2,3):", post("/api/input", {"text":"(1,2,3)","xmin":-10,"xmax":10,"ymin":-10,"ymax":10})[:200])
print("state3d:", get("/api/state3d")[:400])
print("state (2D):", get("/api/state")[:400])
print("input (4,5,0):", post("/api/input", {"text":"(4,5,0)","xmin":-10,"xmax":10,"ymin":-10,"ymax":10})[:200])
print("state3d:", get("/api/state3d")[:500])
