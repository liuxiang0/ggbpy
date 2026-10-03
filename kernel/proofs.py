"""布尔判定与证明命令（共点/共圆/全等/Prove，P2 结构拆分）。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .cmd_util import _resolve, label_of
from .primitives import _prove_cmd
from .prover import SymbolicGeo
from .elements import GeoBoolean, GeoError


__all__ = [
    "_cmd_areconcyclic",
    "_cmd_arecongruent",
    "_cmd_areconcurrent",
    "_cmd_prove",
]


def _cmd_areconcyclic(cons, defn, args):
    return _prove_cmd(cons, defn, args, "concyclic", 4)

def _cmd_arecongruent(cons, defn, args):
    return _prove_cmd(cons, defn, args, "congruent", 2)

def _cmd_areconcurrent(cons, defn, args):
    return _prove_cmd(cons, defn, args, "concurrent", 3)

def _cmd_prove(cons, defn, args):
    """Prove[b]：对 Are* 生成的布尔元素重新证明并生成新元素。"""
    if len(args) != 1:
        raise GeoError("Prove 需要一个布尔命题")
    el = _resolve(cons, args[0])
    if el.kind != "boolean" or not getattr(el, "_prove_args", None):
        raise GeoError("Prove 的参数必须是 AreParallel 等命题")
    kind, labels = el._prove_args
    from .prover import SymbolicGeo
    sg = SymbolicGeo(cons)
    res = sg.prove(kind, labels)
    new_el = GeoBoolean(label_of(defn), defn)
    new_el.free = False
    new_el.value = res.value
    new_el.detail = res.detail
    return cons.add(new_el)
