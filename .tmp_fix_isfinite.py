"""IsFinite：用 sympy 的 is_finite 谓词（正确处理 zoo/nan/oo），并支持 ∞/oo/inf 文本。"""
from pathlib import Path

p = Path("kernel/numeric.py")
s = p.read_text(encoding="utf-8")
assert len(s) > 3000, len(s)
old = '''    lab = body.strip()
    el = cons.elements.get(lab) if lab else None
    if el is not None and el.kind in ("number",):
        v = getattr(el, "value", None)
        return isinstance(v, (int, float)) and math.isfinite(float(v))
    try:
        e = _parse_sympy(body, {}, cons)
        v = float(sympy.N(e))
    except Exception as ex:  # 含自由符号/无法数值化：明确报错而不是猜
        raise GeoError("IsFinite 需要一个可求值的数值或表达式：" + str(ex)[:60])
    return math.isfinite(v)'''
new = '''    lab = body.strip()
    el = cons.elements.get(lab) if lab else None
    if el is not None and el.kind in ("number",):
        v = getattr(el, "value", None)
        return isinstance(v, (int, float)) and math.isfinite(float(v))
    # 无穷文本（∞/oo/inf）直接判定
    txt = lab.replace(" ", "").lower().lstrip("+-")
    if txt in ("∞", "oo", "inf", "infinity"):
        return False
    try:
        e = _parse_sympy(body.replace("∞", "oo"), {}, cons)
    except Exception as ex:  # 无法解析：明确报错而不是猜
        raise GeoError("IsFinite 需要一个可求值的数值或表达式：" + str(ex)[:60])
    # sympy 谓词优先：zoo（1/0）/nan 都是 False，且不需要 float 转换
    if e.is_finite is True:
        return True
    if e.is_finite is False:
        return False
    try:
        v = float(sympy.N(e))
    except Exception as ex:  # 含自由符号/无法数值化：明确报错而不是猜
        raise GeoError("IsFinite 需要一个可求值的数值或表达式：" + str(ex)[:60])
    return math.isfinite(v)'''
assert s.count(old) == 1, s.count(old)
p.write_text(s.replace(old, new), encoding="utf-8")
print("IsFinite 已用 is_finite 谓词修正")
