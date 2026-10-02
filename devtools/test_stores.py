#!/usr/bin/env python3
"""内容寻址仓库检测（P2 结构收敛）：图片仓库 / 网格仓库 / 共用 blob_store 逻辑。

用法：python3 -B devtools/test_stores.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel import blob_store, image_store, mesh_store  # noqa: E402

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


print("=== 通用 blob_store ===")
check("content_id 稳定且带前缀",
      blob_store.content_id("x_", "abc") == blob_store.content_id("x_", "abc")
      and blob_store.content_id("x_", "abc").startswith("x_"))
check("不同内容 → 不同 id", blob_store.content_id("x_", "a") != blob_store.content_id("x_", "b"))

print("\n=== 图片仓库 ===")
import base64 as _b64
_PNG_HEX = ("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6300010000050001"
            "0d0a2db40000000049454e44ae426082")
PNG = "data:image/png;base64," + _b64.b64encode(bytes.fromhex(_PNG_HEX)).decode("ascii")
i1 = image_store.put(PNG, 1, 1)
i2 = image_store.put(PNG, 1, 1)
check("相同图片 → 相同 id（内容寻址）", i1 == i2, i1)
check("id 前缀为 img_", i1.startswith("img_"), i1)
check("get 返回记录", (image_store.get(i1) or {}).get("w") == 1)
check("decode 还原 mime 与字节",
      image_store.decode(i1)[0] == "image/png" and len(image_store.decode(i1)[1]) > 10,
      str(image_store.decode(i1)[0]))
try:
    image_store.put("not-a-data-url")
    check("非法图片数据 → 抛错", False, "未抛错")
except ValueError as e:
    check("非法图片数据 → 抛错", "格式" in str(e), str(e)[:30])
ser = image_store.serialize([i1, "img_不存在"])
check("serialize 只导出存在的 id", list(ser.keys()) == [i1], str(list(ser.keys())))
image_store.IMAGES.clear()
n = image_store.load(ser)
check("load 恢复记录", n == 1 and image_store.get(i1) is not None, "n=%d" % n)
image_store.IMAGES.clear()
check("load 跳过坏记录",
      image_store.load({"img_bad": {"w": 1}}) == 0 and image_store.get("img_bad") is None)

print("\n=== 网格仓库 ===")
V = [[0.0, 0.0, 0.0], [1.5, 0.0, 0.0], [0.0, 1.5, 0.0], [0.0, 0.0, 1.5]]
F = [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]]
m1 = mesh_store.put(V, F)
m2 = mesh_store.put([list(v) for v in V], [list(f) for f in F])
check("相同网格 → 相同 id", m1 == m2, m1)
check("id 前缀为 mesh_", m1.startswith("mesh_"), m1)
rec = mesh_store.get(m1)
check("顶点去重（重复点被合并）",
      len(mesh_store.put(V + [[1.5, 0.0, 0.0]], F) and mesh_store.get(mesh_store.put(V + [[1.5, 0, 0]], F))["verts"]) == 4,
      "")
check("面索引重排 + 退化面丢弃",
      mesh_store.get(mesh_store.put(V, [[0, 1, 1, 2], [0, 1]]))["faces"] == [[0, 1, 2]],
      str(mesh_store.get(mesh_store.put(V, [[0, 1, 1, 2], [0, 1]]))["faces"]))
check("edges_of 去重且含环绕边",
      sorted(map(tuple, mesh_store.edges_of([[0, 1, 2]]))) == [(0, 1), (0, 2), (1, 2)],
      str(mesh_store.edges_of([[0, 1, 2]])))
try:
    mesh_store.put([[0, 0, 0], [1, 0, 0]], [])
    check("数据不足 → 抛错", False, "未抛错")
except ValueError:
    check("数据不足 → 抛错", True)
ser_m = mesh_store.serialize([m1])
mesh_store.MESHES.clear()
check("网格 load 恢复并规范化类型",
      mesh_store.load(ser_m) == 1
      and isinstance(mesh_store.get(m1)["verts"][0][0], float)
      and isinstance(mesh_store.get(m1)["faces"][0][0], int))
mesh_store.MESHES.clear()

print("\n=== 两仓库隔离 ===")
image_store.IMAGES.clear()
mesh_store.MESHES.clear()
check("同内容不同仓库互不影响（前缀不同）",
      image_store.put(PNG, 0, 0).startswith("img_") and len(mesh_store.MESHES) == 0
      and len(image_store.IMAGES) == 1)
image_store.IMAGES.clear()

print("\n" + "=" * 56)
print("仓库检测：%d 项断言，%d 失败" % (PASS + FAIL, FAIL))
if FAILED:
    for n in FAILED:
        print("  FAILED: " + n)
    sys.exit(1)
print("结果: ALL PASS")
sys.exit(0)
