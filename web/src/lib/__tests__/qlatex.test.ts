/** 题库 LaTeX → 界面可渲染的 markdown/HTML（KaTeX）。
 *
 *  这里锁的是「题库里真实存在的写法」：`\paren[答案]` 方括号槽、
 *  `\fillin[$\\sqrt[3]{…}$]` 这种带嵌套方括号的答案、嵌套 enumerate、
 *  数学里的 `<`。改这些正则时最容易踩的就是「提前收口」——
 *  预览里会漏出 `$]`、`{\frac{3}{2}}$]` 这类残尾。
 *
 *  ⚠️ 与后端 `amti/latex_ir.py`、`paper.py` 是同一套规则，两边必须一致。
 */
import { describe, expect, it } from 'vitest'
import {
  ANS_RED, figureUrl, redAnswer, showAnswers, stripImageMath, transformOption, transformStem,
} from '@/lib/qlatex'

const RED = '\\textcolor{#d22116}'

describe('redAnswer（答案整段标红）', () => {
  it('空答案返回空串，不产出空的 \\textcolor', () => {
    expect(redAnswer('')).toBe('')
    expect(redAnswer('   ')).toBe('')
  })

  it('纯文字装进 \\text{}，并转义 & % #（否则 KaTeX 直接报错）', () => {
    expect(redAnswer('a&b%c#d')).toBe(`$${RED}{\\text{a\\&b\\%c\\#d}}$`)
  })

  it('答案里的数学原样保留，不再套 \\text', () => {
    expect(redAnswer('$\\frac{1}{2}$')).toBe(`$${RED}{\\frac{1}{2}}$`)
  })

  it('中文 + 数学混排：中文段与数学段各自标红', () => {
    expect(redAnswer('2 或 $\\frac{1}{2}$')).toBe(
      `$${RED}{\\text{2 或 }}$$${RED}{\\frac{1}{2}}$`)
  })

  it('红色与后端 paper.py 的 ANS_RED 同值', () => {
    expect(ANS_RED).toBe('#d22116')
  })
})

describe('showAnswers / stripAnswers（教师版红答案 ↔ 学生版空位）', () => {
  it('\\paren[2]：教师版「（ 红2 ）」，学生版「（　　）」', () => {
    expect(showAnswers('\\paren[2]')).toBe(`（ $${RED}{\\text{2}}$ ）`)
    expect(transformStem('\\paren[2]')).toBe('（　　）')
  })

  it('\\fillin[数学]：教师版只标红公式，学生版是下划线空位', () => {
    expect(showAnswers('\\fillin[$\\frac{1}{2}$]')).toBe(`$${RED}{\\frac{1}{2}}$`)
    expect(transformStem('\\fillin[$\\frac{1}{2}$]')).toBe('＿＿＿＿')
  })

  it('花括号写法 \\fillin{2} 也能处理；\\fillin{} 与裸 \\fillin 是空位', () => {
    expect(showAnswers('\\fillin{2}')).toBe(`$${RED}{\\text{2}}$`)
    expect(showAnswers('\\fillin{}')).toBe('＿＿＿＿')
    expect(showAnswers('\\fillin')).toBe('＿＿＿＿')
    expect(transformStem('答案：\\fillin{2}')).toBe('答案：＿＿＿＿')
  })

  it('槽里的嵌套方括号不会提前收口（\\sqrt[3]{\\frac{3}{2}} 整块取走）', () => {
    const out = showAnswers('\\fillin[$\\sqrt[3]{\\frac{3}{2}}$]')
    expect(out).toBe(`$${RED}{\\sqrt[3]{\\frac{3}{2}}}$`)
    expect(out).not.toContain('$]')          // 漏出的残尾就是预览里的乱码
    expect(out).not.toContain('{\\frac{3}{2}}$]')
  })

  it('内层 \\paren 不参与配对，配平扫描只保证外层不被 [b] 截断', () => {
    expect(showAnswers('\\paren[a \\paren[b]]')).toBe(`（ $${RED}{\\text{a \\paren[b]}}$ ）`)
  })

  it('括号没配平就原样保留（宁可不换，也不吃掉后面的正文）', () => {
    expect(showAnswers('\\paren[abc')).toBe('\\paren[abc')
  })

  it('教师版/学生版对同一道题只差答案，正文一个字不改', () => {
    const q = '已知 $x=2$，则 $x^2$ 的值是 \\paren[4]。'
    expect(transformStem(q)).toBe('已知 $x=2$，则 $x^2$ 的值是 （　　）。')
    expect(transformStem(q, true)).toContain(`（ $${RED}{\\text{4}}$ ）`)
  })
})

describe('宏与定界符归一', () => {
  it('\\R → \\mathbb{R}，\\symbfit{A} → \\boldsymbol{A}', () => {
    expect(transformStem('已知 $\\R$ 与 $\\symbfit{A}$')).toBe('已知 $\\mathbb{R}$ 与 $\\boldsymbol{A}$')
  })

  it('\\[…\\] / \\(…\\) → $$…$$ / $…$', () => {
    expect(transformStem('\\[x+1\\]')).toBe('$$x+1$$')
    expect(transformStem('\\(x+1\\)')).toBe('$x+1$')
  })
})

describe('结构转换', () => {
  it('顶层 enumerate → （1）（2），每问一行', () => {
    expect(transformStem('\\begin{enumerate}\\item 甲\\item 乙\\end{enumerate}'))
      .toBe('（1）甲\n（2）乙')
  })

  it('嵌套 enumerate 用 ①，缩进一层（题库里真实存在小问套小问）', () => {
    const src = '\\begin{enumerate}\\item 甲\\begin{enumerate}\\item a\\end{enumerate}\\item 乙\\end{enumerate}'
    expect(transformStem(src)).toBe('（1）甲\n　①a\n（2）乙')
  })

  it('tabular → markdown 表格（导出的 PDF 与预览同一份内容）', () => {
    expect(transformStem('\\begin{tabular}{cc}a & b\\\\c & d\\end{tabular}'))
      .toBe('| a | b |\n|---|---|\n| c | d |')
  })

  it('句末标点后紧跟的（1）补空行；$…$ 里的 (1) 不动', () => {
    expect(transformStem('结论。 （1）当 $x>0$ 时成立')).toBe('结论。\n\n（1）当 $x\\gt 0$ 时成立')
    expect(transformStem('$S_n(1)$ 与 $a(2)$')).toBe('$S_n(1)$ 与 $a(2)$')
  })
})

describe('数学模式安全', () => {
  it('公式里的 < > 换成 \\lt \\gt（KaTeX 在数学模式里不认裸尖括号）', () => {
    expect(transformStem('当 $x<1$ 时')).toBe('当 $x\\lt 1$ 时')
    expect(transformStem('当 $x>1$ 时')).toBe('当 $x\\gt 1$ 时')
  })

  it('正文里的 < 不动（只改 $…$ 里的）', () => {
    // 紧贴操作数的写法（$c<d$）才是题库常见形态；写成 $c < d$ 时 `\\lt ` 自带
    // 一个空格 + 原空格会变成两个，数学模式里无所谓，这里不锁那种排版细节。
    expect(transformStem('a < b 且 $c<d$')).toBe('a < b 且 $c\\lt d$')
  })

  it('花括号转义 → \\lbrace{} / \\rbrace{}', () => {
    expect(transformStem('\\left\\{ x \\right\\}')).toBe('\\left\\lbrace{} x \\right\\rbrace{}')
  })

  it('公式定界符内侧的空格被去掉（markdown-it 才肯当数学解析）', () => {
    expect(transformStem('公式 $ x+1 $ 结束')).toBe('公式 $x+1$ 结束')
  })
})

describe('图片与图形', () => {
  it('\\includegraphics → <img>，走题库图片接口', () => {
    expect(transformStem('\\includegraphics{a.png}')).toBe('<img src="/api/figure?path=a.png" />')
  })

  it('tikz 图 → 占位文字（导出端不渲染 TikZ）', () => {
    expect(transformStem('\\begin{tikzpicture}\\draw (0,0);\\end{tikzpicture}')).toBe('【图：请手绘】')
  })

  it('选项整条是一张图时先脱 $…$ 定界符，再出 markdown 图片', () => {
    expect(transformOption('$\\includegraphics[width=0.15\\paperwidth]{x.png}$'))
      .toBe('![](/api/figure?path=x.png)')
    expect(stripImageMath('$\\includegraphics{a.png}$')).toBe('\\includegraphics{a.png}')
  })

  it('figureUrl 对中文与空格做 URL 编码', () => {
    expect(figureUrl('图形 1.png')).toBe('/api/figure?path=%E5%9B%BE%E5%BD%A2%201.png')
  })
})

describe('空输入', () => {
  it('空题干 / undefined 类空值不抛错', () => {
    expect(transformStem('')).toBe('')
    expect(transformOption('')).toBe('')
    expect(redAnswer('')).toBe('')
  })
})
