#!/usr/bin/env python3
r"""无地区题：按试卷级映射写 `region`（只改 meta，不动正文）。

输入：
  - 题库评价/地区提取_试卷清单.csv（自动提取）
  - 题库评价/地区提取_未识别卷名_复核.csv（人工复核 69 条）

规则：
  - 人工复核优先；其次 province/city/alias 高置信；
  - 跨省 → region_scope=multi，不写 region；
  - 无信息 → unknown；专题书/书内汇编 → book；
  - 高考真题已有 region，不动。

用法：python3 脚本/元数据_地区.py [--yes]
"""
from __future__ import annotations
import argparse, collections, csv, datetime as _dt, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from amti import store  # noqa: E402

OUT=ROOT/'题库评价'; MAP=ROOT/'数据'/'地区映射.json'; CHANGE=ROOT/'变更记录'
PROV=set('北京 天津 上海 重庆 河北 山西 辽宁 吉林 黑龙江 江苏 浙江 安徽 福建 江西 山东 河南 湖北 湖南 广东 广西 海南 四川 贵州 云南 陕西 甘肃 青海 宁夏 新疆 西藏 内蒙古'.split())
# 自动规则只看第一个命中省份；这几个卷名同时点了多个省/多省学校，必须强制 multi。
FORCE_MULTI = (
    '四省联考', '山西陕西青海宁夏',
    '东北师大附中、哈尔滨师大附中、辽宁省实验中学',
    '广东江西稳派', '南京师大附中、长郡中学、杭州二中',
)

def load_rows():
    auto=list(csv.DictReader(open(OUT/'地区提取_试卷清单.csv',encoding='utf-8-sig')))
    rev={r['paper']:r for r in csv.DictReader(open(OUT/'地区提取_未识别卷名_复核.csv',encoding='utf-8-sig'))}
    return auto,rev

def classify(r,rev):
    b=r['book']; conf=r['confidence']; rv=rev.get(r['paper'])
    text=' '.join([r.get('source_label',''),r.get('paper_title',''),r.get('paper','')])
    if any(x in text for x in FORCE_MULTI):
        return '','multi','auto','low','卷名同时涉及多省/多省学校，按跨省处理'
    if rv:
        if rv['class']=='single':
            return rv['suggest_region'].strip(),'single','manual','medium',rv['reason']
        if rv['class']=='multi':
            return '','multi','manual','low',rv['reason']
        if rv['class']=='book':
            return '','book','manual','low',rv['reason']
        return '','unknown','manual','low',rv['reason']
    if b not in ('模拟题','2024全国优质模拟题精选','手工录入'):
        return '','book','auto','low','专题书/书内汇编，没有单一地区'
    if conf in ('province','city','alias'):
        return r['extracted_region'],'single','auto','high' if conf=='province' else 'medium',f'卷名/来源标签命中（{conf}）'
    if conf=='multi':
        return '','multi','auto','low','跨省联考品牌'
    return '','unknown','auto','low','卷名/标签没有地区信息'

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--yes',action='store_true'); args=ap.parse_args()
    auto,rev=load_rows(); mapping={}; bad=[]
    c=collections.Counter(); q=collections.Counter()
    for r in auto:
        reg,scope,src,conf,reason=classify(r,rev)
        if scope=='single' and reg not in PROV:
            bad.append((r['paper'],reg,reason)); reg=''; scope='unknown'
        mapping[r['paper']]={'region':reg,'scope':scope,'source':src,'confidence':conf,'reason':reason}
        c[(r['book'],scope)]+=1; q[(r['book'],scope)]+=int(r['questions'])
    print('single',sum(v for (b,s),v in c.items() if s=='single'),'papers',
          sum(v for (b,s),v in q.items() if s=='single'),'questions')
    print('scope papers',dict(collections.Counter(s for (b,s),v in c.items() for _ in range(v))))
    print('scope questions',dict(collections.Counter(s for (b,s),v in q.items() for _ in range(v))))
    if bad: print('BAD',bad[:10])
    if not args.yes:
        print('（干跑。确认后加 --yes 落盘）'); return 0
    qs,sig=store.load_for_update(); changed=0
    for x in qs:
        paper=x.key.split('#')[0]
        if x.meta.get('region') or paper not in mapping: continue
        m=mapping[paper]
        if m['scope']=='single':
            x.meta['region']=m['region']
        x.meta['region_scope']=m['scope']
        x.meta['region_source']=m['source']
        x.meta['region_confidence']=m['confidence']
        changed+=1
    store.rewrite_all(qs,based_on=sig)
    MAP.parent.mkdir(parents=True,exist_ok=True)
    MAP.write_text(json.dumps({'generated_at':_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'note':'按试卷/题组映射；目录见 题库评价/地区提取报告.md',
        'papers':mapping},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    CHANGE.mkdir(parents=True,exist_ok=True)
    rep=CHANGE/(_dt.datetime.now().strftime('%Y%m%d_%H%M%S')+'_元数据_地区.md')
    lines=['# 元数据迁移：地区（试卷级）','',
           f'- 时间：{_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
           f'- 写入题目：{changed}',
           f'- 单省：{sum(v for (b,s),v in c.items() if s=="single")} 套 / {sum(v for (b,s),v in q.items() if s=="single")} 题',
           f'- 跨省：{sum(v for (b,s),v in c.items() if s=="multi")} 套 / {sum(v for (b,s),v in q.items() if s=="multi")} 题',
           f'- 无信息：{sum(v for (b,s),v in c.items() if s=="unknown")} 套 / {sum(v for (b,s),v in q.items() if s=="unknown")} 题',
           f'- 专题书：{sum(v for (b,s),v in c.items() if s=="book")} 组 / {sum(v for (b,s),v in q.items() if s=="book")} 题','',
           '## 单省试卷','', '| 试卷 | 省份 | 题数 | 来源 |','|---|---|---:|---|']
    for r in auto:
        m=mapping[r['paper']]
        if m['scope']=='single': lines.append(f"| `{r['paper']}` | {m['region']} | {r['questions']} | {m['source']}/{m['confidence']} |")
    rep.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('✓ written',changed,rep)

if __name__=='__main__': raise SystemExit(main())
