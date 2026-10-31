#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""语义规则库——`analyze.py` 那套字符串规则看不见的缺陷，唯一实现在这里。

两个消费方：`题库评价/analyze.py`（全量评价闸门）与 `题库评价/独立扫描_20261031.py`
（独立扫描 CLI）。**规则只此一份**，谁再抄一份必然分叉（AGENTS.md 的唯一入口规矩）。

只读：不改 `题目/*.tex`、不调模型、不联网。
入口（仓库根目录）：

    python3 题库评价/独立扫描_20261031.py

产物：

    独立扫描_疑点.csv    一行一条疑点，带证据原文，供人工/模型逐条裁决
    独立扫描_统计.json    每类的命中数与分布

为什么要另写一套：2026-10-29 的独立复评已经证明「P0=0 / P1=0 / 全 A」是
`analyze.py` 这套规则的**上限**，不是题库的下限——当时另外查出 14 道 P0、
39 道 P1，并建议给闸门补 8 条规则。`analyze.py` 至今未改（mtime 10-29 00:47，
早于那次复评），所以本轮必须换一套规则再看一遍。

口径：**这里出的是「疑点」，不是「缺陷」**。每条都带证据原文，必须逐条裁决
后才能计入错误率；按规则挑出来的样本不能外推成全库错误率。
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from amti import store  # noqa: E402

OUT = ROOT / "题库评价"

# ── 文本归一：只留下汉字/字母/数字，用来算「解析是不是在抄题干」 ──────
_RE_CMD = re.compile(r"\\[a-zA-Z]+\*?")
_RE_KEEP = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")


def norm(s: str) -> str:
    s = _RE_CMD.sub(" ", s or "")
    return "".join(_RE_KEEP.findall(s))


def bigrams(s: str) -> Counter:
    return Counter(s[i:i + 2] for i in range(len(s) - 1))


def dice(a: str, b: str) -> float:
    """字符二元组 Dice 相似度。空串返回 0。"""
    A, B = bigrams(a), bigrams(b)
    if not A or not B:
        return 0.0
    inter = sum((A & B).values())
    return 2.0 * inter / (sum(A.values()) + sum(B.values()))


def one_line(s: str, n: int = 220) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s if len(s) <= n else s[:n] + "…"


# ── 规则 ─────────────────────────────────────────────────────────────

# 解析自己承认题面坏了。
# ⚠️ 不能收「与题设矛盾」「与条件矛盾」——那是**反证法的正常用语**（实测 68 条里
# 绝大多数是 2011 江苏#19、2013 天津理#19 这类正常证明）。只收明确的「做不了」自述。
RE_BROKEN = re.compile(
    r"无法作答|题面有误|题面.{0,4}有误|无法求解|无法确定答案|无法定项|"
    r"未给出任何备选|未给出.{0,10}(?:选项|备选图形)|没有正确选项|没有备选|均不相同.{0,20}没有正确|"
    r"原卷.{0,4}(?:缺失|缺页)|缺少.{0,16}(?:数据|图|选项|条件).{0,24}无法|"
    r"数据缺失.{0,24}无法判定"
)

# 选择题结论的各种句式（上一轮只认「故选/答案为」，漏了 4 道高考真题）。
# ⚠️ 结论字母常写成「A、C、D」「(A)(C)(D)」「A,C,D」——只抓第一个字母会把
# 正确的多选结论误判成与答案栏不符（实测 19 条里 12 条是这么来的）。
_CONCL_HEAD = (
    r"(?:故选|故选择|所以选|因此选|应选|正确答案(?:应)?为|答案(?:应)?为|"
    r"正确选项(?:应)?为|正确的?选项(?:应)?是|故应选|本题选|综上.{0,6}选)\s*[:：]?\s*"
)
_CONCL_LETTERS = (
    r"[（(]?[ \t]*[A-F]{1,6}[ \t]*[)）]?"
    r"(?:(?:[ \t]*[、，,和与及][ \t]*|[ \t]*|[（(])[ \t]*[A-F]{1,6}[ \t]*[)）]?)*"
)
RE_CONCL = re.compile(_CONCL_HEAD + r"(" + _CONCL_LETTERS + r")")
# 结论后面紧跟「错误/不对」的，是在说「选 C 是错的」，不是结论
RE_CONCL_NEG = re.compile(r"^[ \t]*(?:是|为)?[ \t]*(?:错误|不对|不正确|不行|正确|对)")
# 「题给答案 X」「所给答案 X」——解析在引用（可能是错的）原答案
RE_GIVEN = re.compile(r"(?:题给|所给|原|题中)(?:答案|选项)\s*[:：]?\s*[（(]?\s*([A-F]{1,4})")
# 逐项判定：「A 正确」「D 不应选」「B 错误」
RE_JUDGE = re.compile(
    r"(?:选项\s*)?([A-F])\s*(?:选项)?\s*"
    r"(正确|错误|对|错|不应选|不选|应选|符合|不符合|不成立|成立)"
)
RE_JUDGE_PRE = re.compile(r"(故|所以|因此|可知|易知|显然)?\s*([A-F])\s*(?:正确|错误)")

# 评分细则（散文式，上一轮 RE_SCORE 只认「(2分)」这类）
RE_RUBRIC = re.compile(
    r"不得分|扣分|扣满|评分细则|评分标准|得分点|给分|阅卷|每步.{0,3}分|"
    r"缺少主要条件|逻辑段|酌情给分|答案不唯一.{0,6}给分"
)
# 工作备注 / 校勘话术混进解析。
# ⚠️ 不收「模型」「题库」「录入」这种裸词——「数学模型」「等可能配置模型」是正常
# 题面用语（实测 74 条里 40+ 条是这么误报的）；只收明确的工作话术。
RE_WORKER = re.compile(
    r"待复核|依据源文件|源文件|原册|已打开配图|配图核对|原答案.{0,6}(?:有误|错)|"
    r"正确计算应为|笔误|存疑|识图|OCR|工作备注|未录入|此处未录|无法核实|待确认|"
    r"人工复核|按常见标准结论|题面设置|所给答案.{0,8}应为|原卷.{0,6}印"
)
# 选非题（「下列说法错误的是」）——解析判某项错正是正确答案，不能当矛盾
RE_PICK_WRONG = re.compile(
    r"(?:错误|不正确|不成立|不符合|不满足|不恰当|不可能|不是|不属于|不能)"
    r".{0,12}(?:是|为|有|选|项|结论|命题|说法|个数|序号)|"
    r"(?:选|填|写出).{0,8}(?:错误|不正确|不成立|不符合)|"
    r"错误的?(?:结论|选项|说法|命题|序号|是)|不等式.{0,6}不成立的是|"
    r"假命题|为假的是|不正确的?(?:是|为|有)|真命题的个数"
)
# 页眉页脚 / 整张答案表
RE_PAGE = re.compile(r"数学参考答案|参考答案\s*$|第\s*\d+\s*页|共\s*\d+\s*页|答案速查|题号\s*答案")
# 题干要图
RE_NEEDFIG = re.compile(r"如图|下图|上图|图所示|图象如图|图像如图|如右图|如左图|见图")
RE_HASFIG_ENV = re.compile(r"\\begin\{(?:tikzpicture|tabular|array|center|figure|axis)\}|\\includegraphics|\\fillin")
# 推导痕迹（判「解析只有结果」用；刻意不用 当/若/由/得/设/则/故/即 这种几乎全命中的词）
RE_DERIVE = re.compile(
    r"因为|由于|所以|因此|化简|整理|联立|解得|求导|令\s|代入|配方|判别式|"
    r"单调|分类讨论|不妨设|反证|归纳|构造|两边|平方|开方|移项|通分|约分|"
    r"韦达|均值不等式|柯西|正弦定理|余弦定理|相似|全等|勾股|建系|坐标法|"
    r"设.{0,12}为|记.{0,12}为|证明如下|下面证明|先证|再证"
)
RE_EQ = re.compile(r"=|\\ge|\\le|\\geq|\\leq|\\Rightarrow|\\iff|\\therefore|\\because")

PROVINCES = set(
    "北京 天津 河北 山西 内蒙古 辽宁 吉林 黑龙江 上海 江苏 浙江 安徽 福建 江西 山东 "
    "河南 湖北 湖南 广东 广西 海南 重庆 四川 贵州 云南 西藏 陕西 甘肃 青海 宁夏 新疆".split()
)
RE_REGION_BAD = re.compile(r"满分|考试|时间|分钟|答案|^\d|第.{1,3}页|^\s*$")

# 城市 → 省（用来判「地区与来源标注矛盾」）
CITY_PROV = {
    "南昌": "江西", "赣州": "江西", "九江": "江西", "上饶": "江西", "宜春": "江西",
    "深圳": "广东", "广州": "广东", "东莞": "广东", "佛山": "广东", "珠海": "广东", "惠州": "广东", "汕头": "广东", "湛江": "广东", "肇庆": "广东", "江门": "广东", "茂名": "广东", "梅州": "广东", "清远": "广东", "韶关": "广东", "中山": "广东",
    "青岛": "山东", "济南": "山东", "烟台": "山东", "潍坊": "山东", "临沂": "山东", "淄博": "山东", "济宁": "山东", "泰安": "山东", "威海": "山东", "德州": "山东", "聊城": "山东", "滨州": "山东", "菏泽": "山东", "枣庄": "山东", "日照": "山东", "东营": "山东",
    "杭州": "浙江", "宁波": "浙江", "温州": "浙江", "绍兴": "浙江", "嘉兴": "浙江", "湖州": "浙江", "金华": "浙江", "衢州": "浙江", "台州": "浙江", "丽水": "浙江", "舟山": "浙江",
    "南京": "江苏", "苏州": "江苏", "无锡": "江苏", "常州": "江苏", "南通": "江苏", "徐州": "江苏", "盐城": "江苏", "扬州": "江苏", "镇江": "江苏", "泰州": "江苏", "淮安": "江苏", "连云港": "江苏", "宿迁": "江苏",
    "合肥": "安徽", "芜湖": "安徽", "蚌埠": "安徽", "阜阳": "安徽", "安庆": "安徽", "马鞍山": "安徽", "滁州": "安徽", "宿州": "安徽", "六安": "安徽", "亳州": "安徽", "宣城": "安徽", "铜陵": "安徽", "淮北": "安徽", "淮南": "安徽", "黄山": "安徽", "池州": "安徽",
    "武汉": "湖北", "宜昌": "湖北", "襄阳": "湖北", "荆州": "湖北", "黄冈": "湖北", "孝感": "湖北", "十堰": "湖北", "荆门": "湖北", "鄂州": "湖北", "黄石": "湖北", "咸宁": "湖北", "随州": "湖北", "恩施": "湖北", "天门": "湖北", "仙桃": "湖北", "潜江": "湖北",
    "长沙": "湖南", "株洲": "湖南", "湘潭": "湖南", "衡阳": "湖南", "岳阳": "湖南", "常德": "湖南", "郴州": "湖南", "娄底": "湖南", "邵阳": "湖南", "益阳": "湖南", "永州": "湖南", "怀化": "湖南", "张家界": "湖南",
    "福州": "福建", "厦门": "福建", "泉州": "福建", "漳州": "福建", "莆田": "福建", "龙岩": "福建", "三明": "福建", "南平": "福建", "宁德": "福建",
    "成都": "四川", "绵阳": "四川", "德阳": "四川", "南充": "四川", "宜宾": "四川", "泸州": "四川", "达州": "四川", "乐山": "四川", "遂宁": "四川", "内江": "四川", "自贡": "四川", "攀枝花": "四川", "广元": "四川", "眉山": "四川", "广安": "四川", "雅安": "四川", "巴中": "四川", "资阳": "四川",
    "郑州": "河南", "洛阳": "河南", "开封": "河南", "新乡": "河南", "南阳": "河南", "许昌": "河南", "平顶山": "河南", "安阳": "河南", "焦作": "河南", "商丘": "河南", "信阳": "河南", "周口": "河南", "驻马店": "河南", "漯河": "河南", "三门峡": "河南", "濮阳": "河南", "鹤壁": "河南",
    "石家庄": "河北", "唐山": "河北", "保定": "河北", "邯郸": "河北", "秦皇岛": "河北", "张家口": "河北", "承德": "河北", "廊坊": "河北", "沧州": "河北", "衡水": "河北", "邢台": "河北",
    "太原": "山西", "大同": "山西", "临汾": "山西", "运城": "山西", "晋中": "山西", "长治": "山西", "晋城": "山西", "吕梁": "山西", "忻州": "山西", "朔州": "山西", "阳泉": "山西",
    "沈阳": "辽宁", "大连": "辽宁", "鞍山": "辽宁", "抚顺": "辽宁", "锦州": "辽宁", "营口": "辽宁", "丹东": "辽宁", "盘锦": "辽宁", "葫芦岛": "辽宁", "阜新": "辽宁", "辽阳": "辽宁", "铁岭": "辽宁", "朝阳": "辽宁", "本溪": "辽宁",
    "长春": "吉林", "吉林市": "吉林", "四平": "吉林", "延边": "吉林", "松原": "吉林", "白城": "吉林", "通化": "吉林", "白山": "吉林", "辽源": "吉林",
    "哈尔滨": "黑龙江", "齐齐哈尔": "黑龙江", "大庆": "黑龙江", "牡丹江": "黑龙江", "佳木斯": "黑龙江", "绥化": "黑龙江", "鸡西": "黑龙江", "鹤岗": "黑龙江", "双鸭山": "黑龙江", "伊春": "黑龙江", "黑河": "黑龙江",
    "西安": "陕西", "咸阳": "陕西", "宝鸡": "陕西", "渭南": "陕西", "汉中": "陕西", "榆林": "陕西", "延安": "陕西", "安康": "陕西", "商洛": "陕西", "铜川": "陕西",
    "兰州": "甘肃", "天水": "甘肃", "白银": "甘肃", "庆阳": "甘肃", "平凉": "甘肃", "酒泉": "甘肃", "张掖": "甘肃", "武威": "甘肃", "定西": "甘肃", "陇南": "甘肃",
    "昆明": "云南", "曲靖": "云南", "大理": "云南", "玉溪": "云南", "红河": "云南", "昭通": "云南", "楚雄": "云南", "保山": "云南", "文山": "云南", "普洱": "云南", "临沧": "云南", "丽江": "云南",
    "贵阳": "贵州", "遵义": "贵州", "毕节": "贵州", "六盘水": "贵州", "安顺": "贵州", "铜仁": "贵州", "黔南": "贵州", "黔东南": "贵州", "黔西南": "贵州",
    "南宁": "广西", "柳州": "广西", "桂林": "广西", "玉林": "广西", "梧州": "广西", "北海": "广西", "钦州": "广西", "贵港": "广西", "百色": "广西", "河池": "广西", "来宾": "广西", "贺州": "广西", "防城港": "广西", "崇左": "广西",
    "海口": "海南", "三亚": "海南", "儋州": "海南",
    "呼和浩特": "内蒙古", "包头": "内蒙古", "赤峰": "内蒙古", "鄂尔多斯": "内蒙古", "通辽": "内蒙古", "呼伦贝尔": "内蒙古", "巴彦淖尔": "内蒙古", "乌兰察布": "内蒙古", "乌海": "内蒙古",
    "银川": "宁夏", "石嘴山": "宁夏", "吴忠": "宁夏", "固原": "宁夏", "中卫": "宁夏",
    "西宁": "青海", "海东": "青海",
    "乌鲁木齐": "新疆", "昌吉": "新疆", "伊犁": "新疆", "喀什": "新疆", "阿克苏": "新疆", "巴音郭楞": "新疆", "克拉玛依": "新疆", "哈密": "新疆", "吐鲁番": "新疆", "石河子": "新疆",
    "拉萨": "西藏", "日喀则": "西藏",
}


def region_of_label(label: str) -> set[str]:
    """从来源标注里抽省份（省名直给 + 城市名映射）。"""
    out = {p for p in PROVINCES if p in label}
    for city, prov in CITY_PROV.items():
        if city in label:
            out.add(prov)
    return out


# ── 本轮（2026-10-31）新增的三条轴 ──────────────────────────────
# 都是 analyze.py 完全没有的；命中后经独立裁决 22/22、30/30 成立。

# 单选题却自述多个选项成立。22 命中全真，其中 14 道至今仍标 single_choice。
# 根因：`_images` 三本书的「试卷」字段是扫描页号，新高考第 9–11 题（多选）
# 被按单选录入，只能挑一个字母，解析只好写「题面疑似有误」。
RE_MULTI_ADMIT = re.compile(
    r"按单选|作为单选题|单选题.{0,12}(?:均成立|都成立|多解|有误|瑕疵)|"
    r"均成立.{0,12}单选|题面疑似有误|本题实际为多选|实为多选|"
    r"多正确项|两项皆真|三个正确选项|两项同时成立"
)


def _half_duplicate(sol: str) -> float:
    """解析前后两半的字符二元组相似度。>0.9 视为整段重复粘贴。"""
    n = norm(sol)
    if len(n) < 200:
        return 0.0
    h = len(n) // 2
    return dice(n[:h], n[h:])


# ── 答案归一：比「两题答案是否不同」之前必须先归一 ────────────────
# 实测教训（2026-10-31 G06 批 15 对全是形式差异）：`\dfrac` vs `\frac`、
# `\left[1,2\right)` vs `[1,2)`、`$ $` 包裹、空白与全半角标点，都会让
# 逐字比较判成「答案不同」，把合法重复题全灌进待查队列。
_RE_DFRAC = re.compile(r"\\[dt]frac")
_RE_LR = re.compile(r"\\(?:left|right|!|,|;|:|quad|qquad|text|mbox|displaystyle)")
_RE_SP = re.compile(r"[\s$\u3000]")
_PUNCT_N = str.maketrans({"（": "(", "）": ")", "，": ",", "、": ",", "；": ";",
                          "：": ":", "。": ".", "　": ""})


def ans_canon(a: str) -> str:
    r"""把答案折成「只按数学含义比」的规范串。"""
    s = _RE_LR.sub("", (a or ""))
    s = _RE_DFRAC.sub(r"\\frac", s)
    s = s.translate(_PUNCT_N)
    return _RE_SP.sub("", s)


def _answer_conflict(q1, q2) -> bool:
    r"""两题答案是否**真的**不同（排除形式差异与题型口径差异）。"""
    a1, a2 = ans_canon(q1.answer), ans_canon(q2.answer)
    if not a1 or not a2 or a1 == a2:
        return False
    # 选择题字母 vs 填空/解答的值：题型口径不同，不是答案冲突
    letters = set("ABCDEF")
    for x, y in ((a1, a2), (a2, a1)):
        if set(x) <= letters and not (set(y) <= letters):
            return False
    if "见解析" in a1 or "见解析" in a2:
        return False
    return True


def scan(q, by_key):
    """返回 [(code, level, evidence)]。level 只是**建议**级别，裁决后才算数。"""
    hits = []
    stem, sol, ans = q.stem or "", q.solution or "", (q.answer or "").strip()
    nstem, nsol = norm(stem), norm(sol)
    is_choice = q.type in ("single_choice", "multi_choice")
    opts = {o.label: (o.text or "") for o in q.options}

    def add(code, level, ev):
        hits.append((code, level, ev))

    # ── P0 类 ──
    m = RE_BROKEN.search(sol)
    if m:
        i = m.start()
        add("sol_admits_broken", "P0", one_line(sol[max(0, i - 60):i + 90], 200))

    if is_choice and ans and re.fullmatch(r"[A-F]{1,4}", ans):
        pick_wrong = bool(RE_PICK_WRONG.search(stem))
        concl = []
        for m in RE_CONCL.finditer(sol):
            if RE_CONCL_NEG.match(sol[m.end():m.end() + 8]):
                continue  # 「故选 C 错误」——不是说选 C
            letters = "".join(re.findall(r"[A-F]", m.group(1)))
            if letters:
                concl.append((letters, m.start()))
        bad = [(c, i) for c, i in concl if set(c) != set(ans)]
        if bad:
            c, i = bad[-1]
            add("ans_vs_sol_conclusion", "P0",
                f"答案栏 {ans}；解析第 {i} 字处结论 {c}：{one_line(sol[max(0,i-50):i+70],180)}")
        # 逐项判定与答案栏冲突。选非题（问「错误的是」）一律跳过：判某项错正是答案。
        if not pick_wrong:
            pos, neg = set(), set()
            for m in RE_JUDGE.finditer(sol):
                letter, word = m.group(1), m.group(2)
                if letter not in opts:
                    continue
                # 「假设 C 成立」「若 C 成立」是反证法开头，不是判定
                if re.search(r"假设|若|如果|不妨", sol[max(0, m.start() - 6):m.start()]):
                    continue
                if word in ("正确", "对", "应选", "符合", "成立"):
                    pos.add(letter)
                elif word in ("错误", "错", "不应选", "不选", "不符合", "不成立"):
                    neg.add(letter)
            if neg & set(ans) and not (pos & set(ans)):
                add("sol_rejects_answer", "P0",
                    f"答案栏 {ans} 含 {''.join(sorted(neg & set(ans)))}，但解析判它错：{one_line(sol[:170],170)}")
            # 只有「每个选项都被判过」时，正确项集合才足以当第二证人
            if q.type == "multi_choice" and pos and (pos | neg) == set(opts) and pos != set(ans):
                add("sol_pos_set_differs", "P0",
                    f"答案栏 {ans}；解析逐项判正确 {''.join(sorted(pos))}／判错误 {''.join(sorted(neg))}")

    # 题干与解析对调
    if (RE_CONCL.search(stem) or re.search(r"^\s*(?:解|证明|解答)[:：]", stem)) and \
            re.search(r"[？?]\s*$|____|\\fillin|\\paren", sol) and len(nsol) < len(nstem) * 0.6:
        add("stem_sol_swapped", "P0", f"题干含解答痕迹、解析像题面：{one_line(sol,140)}")

    # 选项图不全：选项里引用了图，但不是每个选项都有
    if is_choice and opts:
        img_opts = [l for l, t in opts.items() if "\\includegraphics" in t]
        if img_opts and len(img_opts) < len(opts):
            add("option_figure_partial", "P0",
                f"{len(opts)} 个选项里只有 {len(img_opts)} 个带图（{''.join(sorted(img_opts))}），其余选项文本："
                + one_line("／".join(f"{l}.{opts[l]}" for l in sorted(opts) if l not in img_opts), 140))
        empty = [l for l, t in opts.items()
                 if not re.sub(r"[\s$\\{}&]", "", t or "")]
        if empty and not img_opts:
            add("option_text_empty", "P0", f"选项 {''.join(sorted(empty))} 没有任何可见内容")

    # ── P1 类 ──
    if q.type != "detailed_answer" and ans in ("{}", "无", "略", "答案：{}", "$ $", "见解析", ""):
        add("answer_degenerate", "P0", f"客观题答案栏是 {ans!r}")
    if nsol and nstem:
        d = dice(nstem, nsol)
        if d > 0.90 and len(nsol) < len(nstem) * 1.6:
            add("sol_copies_stem", "P1", f"相似度 {d:.3f}，解析/题干长度比 {len(nsol)/max(1,len(nstem)):.2f}：{one_line(sol,160)}")

    if q.type == "detailed_answer" and nsol:
        nder = len(RE_DERIVE.findall(sol))
        neq = len(RE_EQ.findall(sol))
        # 只有结果：没有推导词、等式链也短
        if nder == 0 and neq <= 2 and len(nsol) < 400:
            add("sol_result_only", "P1", f"推导词 0、等号 {neq}、归一长度 {len(nsol)}：{one_line(sol,200)}")

    rub = RE_RUBRIC.findall(sol)
    if len(rub) >= 2 or (rub and len(nsol) < 300):
        add("sol_scoring_rubric", "P1", f"评分用语 {len(rub)} 处 {sorted(set(rub))}：{one_line(sol,180)}")

    wk = RE_WORKER.search(sol)
    if wk:
        i = wk.start()
        add("sol_worker_note", "P1", one_line(sol[max(0, i - 50):i + 90], 180))

    pg = RE_PAGE.search(sol)
    if pg:
        i = pg.start()
        add("sol_page_noise", "P1", one_line(sol[max(0, i - 40):i + 80], 160))

    if RE_NEEDFIG.search(stem) and not q.figures and not RE_HASFIG_ENV.search(stem):
        add("figure_needed_absent", "P1", one_line(stem, 180))

    # 重复题但答案不同（高相似度才可疑；文/理卷数字不同是合法的）
    tgt = q.meta.get("dup_of")
    if tgt and tgt in by_key:
        other = by_key[tgt]
        a1, a2 = norm(ans), norm(other.answer or "")
        try:
            score = float(q.meta.get("dup_score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        if (a1 and a2 and a1 != a2 and score >= 0.93 and _answer_conflict(q, other)
                and not q.meta.get("dup_answer_variant")
                and not other.meta.get("dup_answer_variant")):
            add("dup_answer_diff_high", "P1",
                f"dup_score {score}；本题 {one_line(ans,60)} vs {tgt} {one_line(other.answer,60)}")

    # ── 元数据 ──
    region = (q.meta.get("region") or "").strip()
    if region and re.search(r"满分|考试时间|分钟|答案|第.{1,3}页", region):
        add("region_garbage", "P2", f"region={region!r}（版面噪声）")
    elif region and re.match(r"^\d{4}", region):
        add("region_format_anomaly", "P3", f"region={region!r}（年份混进地区字段，筛选会碎成多值）")
    label = q.meta.get("source_label") or ""
    if region and region in PROVINCES and label:
        provs = region_of_label(label)
        if provs and region not in provs:
            add("region_vs_label", "P2", f"region={region}；source_label={one_line(label,90)} → {sorted(provs)}")
    if tgt and tgt not in by_key and tgt != q.key:
        add("dup_of_dangling", "P2", f"dup_of 指向不存在的 key：{tgt}")
    if isinstance(q.meta.get("stars"), int) and q.meta["stars"] == 0:
        add("meta_stars_zero", "P3", "meta.stars=0（界面显示未评级）")
    if re.search(r"\d+\s*分", ans) and q.type != "detailed_answer":
        add("answer_has_score", "P2", f"答案栏带分值：{one_line(ans,80)}")

    # ── 本轮新增三条轴 ──
    # ⚠️「正确的有几项？」是**数个数**的单选题（选项是「0项/1项/2项/3项」），
    # 不是多选。实测误报过 辽宁多校调研#4，必须排掉「有几项/有多少个/个数」。
    if q.type == "single_choice" and not re.search(
            r"正确的有\s*[几多]|正确的个数|正确的项数|有几项|有多少项", stem) \
            and re.search(
            r"（多选）|\(多选\)|多选题|下列结论正确的有|下列说法正确的有|"
            r"下列命题正确的有|正确的有|不正确的有|错误的有", stem):
        add("type_stem_mismatch", "P0",
            "题干是多选措辞（「正确的有」/「（多选）」）但题型标 single_choice：" + one_line(stem, 120))
    if q.type == "single_choice":
        mm = RE_MULTI_ADMIT.search(sol)
        if mm:
            i = mm.start()
            add("single_choice_multi_admit", "P0",
                "单选题但解析自述多解：" + one_line(sol[max(0, i - 50):i + 90], 180))
    dh = _half_duplicate(sol)
    if dh > 0.90:
        add("sol_duplicated_half", "P1",
            f"解析前后两半相似度 {dh:.3f}（整段重复粘贴），解析长 {len(sol)}")
    if is_choice:
        sets = []
        for mm in RE_CONCL.finditer(sol):
            if RE_CONCL_NEG.match(sol[mm.end():mm.end() + 8]):
                continue
            L = "".join(sorted(set(re.findall(r"[A-F]", mm.group(1)))))
            if L:
                sets.append(L)
        if len(set(sets)) >= 2:
            add("sol_multi_conclusion", "P0",
                f"一份解析里出现 {len(set(sets))} 个不同的选项结论 {sorted(set(sets))}（疑似串题）")
    return hits
