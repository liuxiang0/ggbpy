"""自定义宏（Macro）：把一组构造封装为可复用命令。

宏 = {name, params: [形参标签...], defns: [定义串...], outputs: [输出标签...]}
- 创建：用户从当前构造选择若干自由对象作输入 + 若干输出对象；
  提取输出对象及其依赖子图的定义（按拓扑序），把输入对象标签替换为形参 %1..%n。
- 执行：宏名[实参1,实参2,...] → 形参替换为实参标签 → 逐行 process_internal 重放，
  内部中间对象自动重命名（前缀 _m<name>_），输出对象返回。

线程安全：单线程 FastAPI 服务，注册表为模块级 dict。
"""

import re
from typing import Dict, List

MACROS: Dict[str, dict] = {}


# ---------------------------------------------------------------------------
# 创建宏
# ---------------------------------------------------------------------------

def create_macro(cons, name: str, input_labels: List[str], output_labels: List[str]) -> dict:
    """从当前构造提取宏：输入=自由对象，输出=结果对象（及其依赖子图）。"""
    if not re.match(r"^[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*$", name):
        raise ValueError("宏名需以字母/下划线/中文开头，仅含字母数字下划线中文")
    if name.lower() in ("macro", "macrocreate", "macrodelete", "macrolist"):
        raise ValueError("宏名与保留命令冲突: " + name)
    if name in MACROS:
        raise ValueError("宏 " + name + " 已存在")
    if not output_labels:
        raise ValueError("至少需要一个输出对象")
    if len(set(input_labels)) != len(input_labels):
        raise ValueError("输入对象重复")

    inputs = set()
    for lab in input_labels:
        el = cons.elements.get(lab)
        if el is None:
            raise ValueError("找不到输入对象 " + lab)
        if not el.free:
            raise ValueError("输入对象必须是自由对象: " + lab)
        inputs.add(lab)
    for lab in output_labels:
        if lab not in cons.elements:
            raise ValueError("找不到输出对象 " + lab)

    # 收集依赖子图：从输出沿 deps 向上，遇输入对象停止
    needed = set()
    stack = list(output_labels)
    while stack:
        lab = stack.pop()
        if lab in needed or lab in inputs:
            continue
        needed.add(lab)
        el = cons.elements[lab]
        for d in el.deps:
            stack.append(d.label)

    # 按 order（拓扑序）取需要对象的 defn
    defns = []
    for lab in cons.order:
        if lab in needed:
            defns.append(cons.elements[lab].defn)

    # 把输入标签替换为形参 %1..%n（整 token 匹配，避免子串误替换）
    params = input_labels
    for i, lab in enumerate(params, 1):
        param = "%" + str(i)
        defns = [_replace_token(d, lab, param) for d in defns]

    macro = {
        "name": name,
        "params": params,
        "defns": defns,
        "outputs": [o for o in output_labels if o not in inputs],
    }
    MACROS[name] = macro
    return macro


# 匹配普通标识符 或 %N 形参
_TOKEN_RE = re.compile(r"%\d+|[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*")


def _replace_token(text: str, old: str, new: str) -> str:
    """把 text 中独立的 token old 替换为 new（不破坏字符串内/数字内）。"""
    def _sub(m):
        return new if m.group(0) == old else m.group(0)
    return _TOKEN_RE.sub(_sub, text)


# ---------------------------------------------------------------------------
# 执行宏
# ---------------------------------------------------------------------------

def run_macro(cons, name: str, arg_labels: List[str], out_label: str = None):
    """执行宏：宏名[实参...] → 重放定义序列，返回新建对象列表。
    out_label：命令提供的显式标签（如 cc=宏名[..]），重命名为宏的第一个输出。"""
    macro = MACROS.get(name)
    if macro is None:
        return None
    if len(arg_labels) != len(macro["params"]):
        raise ValueError("宏 " + name + " 需要 " + str(len(macro["params"])) + " 个参数")

    # 参数替换：形参 %i → 实参标签
    lines = macro["defns"]
    for i, arg in enumerate(arg_labels, 1):
        lines = [_replace_token(l, "%" + str(i), arg) for l in lines]

    # 内部对象重命名：defn 左侧标签若非实参 → 加唯一前缀，避免与现有构造冲突
    arg_set = set(arg_labels)
    prefix = "_m" + name + "_"
    renamed = {}
    for line in lines:
        if "=" in line:
            head = line.split("=", 1)[0].strip()
            head_label = head.split("(")[0].strip()
            if head_label and head_label not in arg_set and not head_label.startswith(prefix):
                renamed[head_label] = prefix + head_label
    for old, new in renamed.items():
        lines = [_replace_token(l, old, new) for l in lines]

    # 逐行重放（process_internal 不压撤销栈）
    created = []
    before = set(cons.elements.keys())
    for line in lines:
        cons.process_internal(line)
    # 显式标签：宏的第一个输出重命名为 out_label（若提供）
    if out_label and macro["outputs"]:
        first_out = "_m" + name + "_" + macro["outputs"][0]
        if first_out in cons.elements:
            cons.rename(first_out, out_label)
    for lab in cons.order:
        if lab not in before:
            created.append(cons.elements[lab])
    return created


# ---------------------------------------------------------------------------
# 管理
# ---------------------------------------------------------------------------

def list_macros() -> List[dict]:
    return [{"name": m["name"], "params": list(m["params"]),
             "n_outputs": len(m["outputs"])} for m in MACROS.values()]


def delete_macro(name: str) -> bool:
    if name in MACROS:
        del MACROS[name]
        return True
    return False


def serialize() -> Dict[str, dict]:
    """导出宏（保存/加载用）。"""
    return dict(MACROS)


def load(data: Dict[str, dict]) -> None:
    MACROS.clear()
    for name, m in data.items():
        MACROS[name] = {
            "name": m["name"],
            "params": list(m.get("params", [])),
            "defns": list(m.get("defns", [])),
            "outputs": list(m.get("outputs", [])),
        }
