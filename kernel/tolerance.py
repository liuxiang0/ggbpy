"""统一数值容差（P2/P3）：消除散落在各模块里的 `1e-12` / `1e-9` 等魔数。

分级（数值越小越严格）：

- ``EPSILON``    1e-12  判定「等于 0」的默认容差：叉积、行列式、分母、点积、系数
- ``TIGHT``      1e-15  更严格的零判定（符号化简后、数值噪声更小处）
- ``COORD``      1e-9   坐标 / 长度 / 角度尺度容差：点重合、长度相等、相对量级
- ``ZERO_SQ``    1e-18  平方量（长度²）退化判定，数值上等于 ``COORD ** 2``
- ``LOOSE``      1e-7   含线性化误差的宽松判定（网格面、半空间内点）
- ``COARSE``     1e-6   采样 / 数值拟合 / 最小跨度（曲率分类、等值线、取景）
- ``NEGLIGIBLE`` 1e-300 分母守卫 / 「实际为零」的极小量（非几何容差）
- ``ROOT_TOL``   1e-10  迭代求根收敛阈值
- ``OPT_XATOL`` / ``OPT_FATOL``   scipy 优化器的 x / f 收敛阈值

约定：**新代码不要再写裸 `1e-12` 之类字面量**，`devtools/test_tolerance.py`
会扫描 kernel/ 与 server/ 下的源码并阻止新增（附带自检，防止扫描器失效）。
"""

from __future__ import annotations

EPSILON = 1e-12
"""判定「等于 0」的默认容差（叉积/行列式/分母/点积/系数）。"""

TIGHT = 1e-15
"""更严格的零判定（符号化简后、数值噪声更小处）。"""

COORD = 1e-9
"""坐标 / 长度 / 角度尺度容差（点重合、长度相等、相对量级）。"""

ZERO_SQ = 1e-18
"""平方量退化判定；数值上等于 ``COORD ** 2``（显式写定值，避免浮点乘法末位差异）。"""

LOOSE = 1e-7
"""含线性化误差的宽松判定（网格面、半空间内点）。"""

COARSE = 1e-6
"""采样 / 数值拟合 / 最小跨度（曲率分类、等值线、三维取景）。"""

NEGLIGIBLE = 1e-300
"""分母守卫 / 「实际为零」的极小量（非几何容差）。"""

ROOT_TOL = 1e-10
"""迭代求根（二分/牛顿）收敛阈值。"""

OPT_XATOL = 1e-10
"""scipy 优化器自变量收敛阈值。"""

OPT_FATOL = 1e-14
"""scipy 优化器函数值收敛阈值。"""

# 全部具名容差（供检测脚本遍历）
ALL = {
    "EPSILON": EPSILON, "TIGHT": TIGHT, "COORD": COORD, "ZERO_SQ": ZERO_SQ,
    "LOOSE": LOOSE, "COARSE": COARSE, "NEGLIGIBLE": NEGLIGIBLE,
    "ROOT_TOL": ROOT_TOL, "OPT_XATOL": OPT_XATOL, "OPT_FATOL": OPT_FATOL,
}

# 字面量 → 常量名（供一次性迁移脚本/检测使用）
LITERAL_MAP = {
    "1e-12": "EPSILON", "1e-15": "TIGHT", "1e-9": "COORD", "1e-18": "ZERO_SQ",
    "1e-7": "LOOSE", "1e-6": "COARSE", "1e-300": "NEGLIGIBLE",
    "1e-10": "ROOT_TOL", "1e-14": "OPT_FATOL",
}
