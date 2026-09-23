#!/usr/bin/env python3
r"""预入库体检：扫成品里「Python 控制符吃掉了 LaTeX 命令」造成的静默损坏。

为什么单独一个工具：`录题入库.py` 的 `tidy()` 只还原 0x07/0x08/0x0b/0x0c/0x0d
（\a\b\v\f\r），**故意不动 0x09（Tab）和 0x0a（换行）**。于是非 raw 字符串写出的
`\times` 落成 `<Tab>imes`、`\neq` 落成 `<换行>eq`，而四道闸
（problems / missing_images / spec.after / errors）对这类碎片**全部静默放过**——
实测 114、210 两份带 `\n`/`\t` 碎片的成品干跑都是「干跑通过」，
连修坏了（`\neq` 变成 `\neqeq`）干跑也照样通过。所以这一类必须单独扫。

扫描范围是「题干 / 答案 / 解析 / 选项」四个字段。`选项` 是 2026-09-23 补进来的：
少了它，#252 那道命题否定题选项里的 `\notin` 被吃成真换行，全库扫下来报的是 0。

用法：
    python3 脚本/录题预检控制符.py                 # 只报告，不写文件
    python3 脚本/录题预检控制符.py <成品.json …>   # 只看指定几份（每场收尾前自查用）
    python3 脚本/录题预检控制符.py --apply         # 就地修规则①（逐处打印）

规则①「控制符被吃掉」——三条同时成立才自动修，否则只列出来请人工看：
  a. 控制符前一个字符是数学内容（字母/数字/$/}/]），不是中文标点（那多半是真换行）；
  b. 控制符后面紧跟的片段能补成一条以 \n / \t 开头的命令（最长匹配，见 FRAG）；
  c. 断点处累计 `$` 个数为奇（正处在一对 `$…$` 中间），且不在 cases/array 这类
     合法的多行环境里。
规则②「cases 行分隔符塌陷」——`\\n=3` 被 tidy 的 fake_nl 改成 `\` + 真换行 + `=3`，
变量 `n` 整字符消失。**只报不修**：补回哪个字母要人对着同场别处的平行写法确认。
规则③「裸 %」——LaTeX 里裸 `%` 是**注释符**，必须写 `\%` 才表示这个字符。
`normalize.py` 的「去注释」（`_COMMENT = (?<!\\)%[^\n]*`，作用在题干/答案/解析）
会在入库那一刻把 `%` 到行尾的正文**整段删掉**，而四道闸全部报干净
（2026-09-23 实测 9 场 17 处、单条最多丢 141 字／65 个中文，`spec.after` 与 `errors` 都是 0）。
选项栏「去注释」不看，但裸 `%` 进了 `.tex` 一样坏渲染——`题目/*.tex` 里 `\%` 有 1407 处、裸 `%` **0 处**。
**只报不修**：把 `%` 前补反斜杠由写题的人对着原卷做，工具不猜这里到底是百分号还是杂散注释。
"""
import json, re, sys, glob, argparse

FRAG = {
    0x0a: ['eq', 'eg', 'otin', 'otag', 'ot', 'mid', 'abla', 'atural', 'exists',
           'parallel', 'subseteq', 'vDash', 'sim', 'wline'],
    0x09: ['imes', 'abular', 'anh', 'extstyle', 'ext', 'o', 'op', 'riangle', 'frac', 'ag'],
}
for _k in FRAG:
    FRAG[_k] = sorted(FRAG[_k], key=len, reverse=True)
CTRL2LETTER = {0x0a: 'n', 0x09: 't'}

MATHY = re.compile(r"[A-Za-z0-9$})\]]$")
ENV = r'cases|array|aligned|subarray|matrix|pmatrix|bmatrix|vmatrix|smallmatrix'
OPEN_ENV = re.compile(r'\\begin\{(?:' + ENV + r')\*?\}')
CLOSE_ENV = re.compile(r'\\end\{(?:' + ENV + r')\*?\}')
# 多行环境里行分隔符塌成「单反斜杠 + 换行」
FAKE_ROW = re.compile(r'(?<!\\)((?:\\\\)*)\\\n')
# 规则③：裸 %（前面没有反斜杠）。KaTeX/LaTeX 里它是注释起始，正字要写 \%
BARE_PCT = re.compile(r'(?<!\\)%')
# 「去注释」只遍历这三栏；选项不在其作用域内，但进了 .tex 一样坏
EATEN_FIELDS = ('题干', '答案', '解析')


def in_open_env(text, i):
    return len(OPEN_ENV.findall(text[:i])) > len(CLOSE_ENV.findall(text[:i]))


def scan_field(text):
    """-> (可自动修的断点下标, 需人工看的断点下标, cases 塌陷处下标)"""
    auto, manual, cases = [], [], []
    for ctrl in (0x0a, 0x09):
        for m in re.finditer('\t' if ctrl == 0x09 else '\n', text):
            i = m.start()
            if i == 0:
                continue
            before, after = text[i - 1], text[i + 1:]
            if not MATHY.match(before):
                continue
            if not any(after.startswith(f) for f in FRAG[ctrl]):
                continue
            if text[:i].count('$') % 2 == 1 and not in_open_env(text, i):
                auto.append(i)
            else:
                manual.append(i)
    for m in FAKE_ROW.finditer(text):
        i = m.end() - 2
        if in_open_env(text, i):
            cases.append(i)
    return sorted(set(auto + manual) - set(cases)), sorted(auto), sorted(cases)


def fix_text(text):
    _, auto, _ = scan_field(text)
    if not auto:
        return text, 0
    out, prev = [], 0
    for i in auto:
        out.append(text[prev:i])
        out.append('\\' + CTRL2LETTER[ord(text[i])])   # 控制符 → 反斜杠 + 命令首字母，残形原样留着
        prev = i + 1
    out.append(text[prev:])
    return ''.join(out), len(auto)


def fields(rec):
    # 「选项」必须在列：它是选项类题里唯一会被写坏的地方，漏扫过一次
    # （#252 #4 的 `$\forall x\notin\mathbf{R}$` 落成 `$\forall x`+真换行+`otin…`，脚本报 0）
    for k in ('题干', '答案', '解析', '选项'):
        v = rec.get(k)
        if isinstance(v, dict):
            for kk in v:
                yield k, kk, v[kk]
        elif isinstance(v, str):
            yield k, None, v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    paths = a.paths or sorted(glob.glob('数据/录题/输出_v2/*.成品.json'))

    ta = tm = tc = tp = 0
    touched = 0
    for path in paths:
        recs = json.load(open(path, encoding='utf-8'))
        body = recs.get('questions', []) if isinstance(recs, dict) else recs
        name = path.split('/')[-1]
        n_auto = n_man = n_case = n_pct = 0
        for r in body:
            for k, kk, s in fields(r):
                if not isinstance(s, str):
                    continue
                hits, auto, cases = scan_field(s)
                n_auto += len(auto)
                n_man += len(hits) - len(auto)
                n_case += len(cases)
                for i in cases:
                    print('  %s #%s %s ①cases 行分隔符塌陷：…%s' % (name[:28], r.get('题号'), k, repr(s[max(0, i - 40):i + 24])))
                for m in BARE_PCT.finditer(s):
                    n_pct += 1
                    print('  %s #%s %s ③裸%%：…%s' % (
                        name[:28], r.get('题号'), k, repr(s[max(0, m.start() - 30):m.start() + 20])))
                    print('     %s' % ('→「去注释」会把它到行尾的内容整段删掉，入库即丢正文——写成 \\%'
                                        if k in EATEN_FIELDS else
                                        '→ 选项栏不被「去注释」吃，但裸 % 进 .tex 会截断渲染——写成 \\%'))
                if auto and a.apply:
                    if kk is None:
                        r[k] = fix_text(s)[0]
                    else:
                        r[k][kk] = fix_text(s)[0]
        if n_auto or n_man or n_case or n_pct:
            touched += 1
            print('%-62s 被吃控制符 %2d 处（可自动修 %2d）/ cases 塌陷 %d 处 / 裸%% %d 处%s'
                  % (name[:62], n_auto + n_man, n_auto, n_case, n_pct,
                     '  ← 已写回' if a.apply and n_auto else ''))
        if a.apply and n_auto:
            open(path, 'w', encoding='utf-8').write(json.dumps(recs, ensure_ascii=False, indent=1))
        ta += n_auto
        tm += n_man
        tc += n_case
        tp += n_pct
    print('扫 %d 份成品：%d 份有问题；可自动修 %d 处、需人工看 %d 处、cases 塌陷 %d 处、裸%% %d 处%s'
          % (len(paths), touched, ta, tm, tc, tp, '（已写回）' if a.apply else '（未写回）'))
    if tp:                       # 规则③ 只报不修，--apply 也不放过
        return 1
    return 1 if (tm or tc) and not a.apply else 0


sys.exit(main())
