"""AmTiKu · 搜索框语法

只做**一层薄解析**，不改变命中口径：解析出的字段最终仍交给
`amti.web.query.QuestionFilter`，列表与组卷共用。

支持：

    考点:三角 年份:2024 类型:多选 难度:中档 出处:新高考I卷 地区:江苏
    考点:函数&导数           # `&` = **交集**：这题要同时挂这两个考点
    -导数                    # 排除含“导数”的题
    出处:"2024 新高考I卷"    # 引号把空格并进一个字段值

字段别名：point/考点/知识点、year/年份、type/类型/题型、
difficulty/难度、source/出处/来源、region/地区。

**引号只负责把空格并进一个 token**；关键词仍按现有 `kw_hit` 的多词 AND
处理，不做“精确短语”语义——那会改变列表与组卷的命中口径。
"""
from __future__ import annotations

from dataclasses import dataclass

_FIELDS = {
    "考点": "point", "知识点": "point", "point": "point", "kp": "point",
    "年份": "year", "year": "year",
    "类型": "type", "题型": "type", "type": "type",
    "难度": "difficulty", "difficulty": "difficulty",
    "出处": "source", "来源": "source", "source": "source", "卷": "source",
    "地区": "region", "region": "region",
}

_TYPE = {
    "单选": "single_choice", "单选题": "single_choice",
    "single_choice": "single_choice",
    "多选": "multi_choice", "多选题": "multi_choice",
    "multi_choice": "multi_choice",
    "填空": "fill_in_blank", "填空题": "fill_in_blank",
    "fill_in_blank": "fill_in_blank",
    "解答": "detailed_answer", "解答题": "detailed_answer",
    "detailed_answer": "detailed_answer",
}

_DIFF = {
    "简单": "简单题", "简单题": "简单题",
    "中档": "中档题", "中档题": "中档题",
    "难": "难题", "难题": "难题",
}


@dataclass(frozen=True)
class ParsedQuery:
    keyword: str = ""
    exclude: tuple[str, ...] = ()
    point: str = ""
    #: 考点怎么算命中：`any`（默认，命中任一） / `all`（交集，全部都要挂）。
    #: 语法里只要有一个考点值用了 `&`（如 `考点:函数&导数`）就是 `all`。
    point_mode: str = ""
    year: str = ""
    type: str = ""
    difficulty: str = ""
    source: str = ""
    region: str = ""

    @property
    def has_fields(self) -> bool:
        return any((self.point, self.year, self.type, self.difficulty,
                    self.source, self.region))


def _split(text: str) -> list[str]:
    """按空白切词；双引号内的空白不切，引号本身去掉。"""
    out: list[str] = []
    buf: list[str] = []
    quote = False
    for ch in text or "":
        if ch == '"':
            quote = not quote
            continue
        if ch.isspace() and not quote:
            if buf:
                out.append("".join(buf))
                buf = []
            continue
        buf.append(ch)
    if buf:
        out.append("".join(buf))
    return out


def parse(q: str) -> ParsedQuery:
    vals: dict[str, str] = {}
    words: list[str] = []
    exclude: list[str] = []
    point_all = False

    for tok in _split(q):
        tok = tok.strip()
        if not tok:
            continue
        if tok.startswith("-") and len(tok) > 1:
            neg = tok[1:].strip()
            if neg and ":" not in neg:
                exclude.append(neg)
            continue
        if ":" in tok:
            key, val = tok.split(":", 1)
            key = key.strip().lower()
            val = val.strip()
            fld = _FIELDS.get(key)
            if fld and val:
                if fld == "type":
                    val = ",".join(_TYPE.get(x.strip(), x.strip())
                                   for x in val.split(",") if x.strip())
                elif fld == "difficulty":
                    val = ",".join(_DIFF.get(x.strip(), x.strip())
                                   for x in val.split(",") if x.strip())
                elif fld == "point" and "&" in val:
                    # `考点:函数&导数` = 交集。语义只做一个标记，真正的
                    # 判定在 QuestionFilter（列表与组卷共用同一口径）。
                    parts = [x.strip() for x in val.split("&") if x.strip()]
                    if len(parts) > 1:
                        point_all = True
                    val = ",".join(parts)
                vals[fld] = (vals[fld] + "," + val).strip(",") if fld in vals else val
                continue
        words.append(tok)

    return ParsedQuery(
        keyword=" ".join(words),
        exclude=tuple(dict.fromkeys(exclude)),
        point=vals.get("point", ""),
        point_mode="all" if point_all else "",
        year=vals.get("year", ""),
        type=vals.get("type", ""),
        difficulty=vals.get("difficulty", ""),
        source=vals.get("source", ""),
        region=vals.get("region", ""),
    )


def _selftest() -> int:
    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        print(("  ✓ " if cond else "  ✗ ") + name + (("  " + extra) if extra else ""))
        if not cond:
            fails += 1

    p = parse('考点:三角 年份:2024 类型:多选 难度:中档 -导数 函数')
    check("字段与关键词分离",
          p.point == "三角" and p.year == "2024" and p.keyword == "函数",
          repr(p))
    check("类型中文映射", p.type == "multi_choice", p.type)
    check("难度中文映射", p.difficulty == "中档题", p.difficulty)
    check("排除词", p.exclude == ("导数",), str(p.exclude))
    p2 = parse('出处:"2024 新高考I卷" -解析')
    check("引号并空格", p2.source == "2024 新高考I卷", repr(p2.source))
    check("引号外仍切词", p2.keyword == "" and p2.exclude == ("解析",), repr(p2))
    p3 = parse("6.4.2")
    check("题号不误判字段", p3.keyword == "6.4.2" and not p3.has_fields, repr(p3))
    p4 = parse("年份:2024,2025 年份:2026")
    check("同字段取并集", p4.year == "2024,2025,2026", p4.year)
    p5 = parse("考点:函数&导数 年份:2024")
    check("& 表示考点交集",
          p5.point == "函数,导数" and p5.point_mode == "all", repr(p5))
    p6 = parse("考点:函数,导数")
    check("逗号仍是并集", p6.point == "函数,导数" and p6.point_mode == "", repr(p6))
    p7 = parse("考点:函数&导数&数列")
    check("多个 & 仍是一组交集",
          p7.point == "函数,导数,数列" and p7.point_mode == "all", repr(p7))
    print("query_syntax 自检 %s（%d 项失败）"
          % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
