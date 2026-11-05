#!/usr/bin/env python3
"""给题目打质量标记：重复题 / 低清图（只写 meta）。"""
from __future__ import annotations
import argparse, collections, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from amti import store  # noqa: E402
from PIL import Image
IMG=ROOT/'图片'
def norm(s): return re.sub(r'\s+','',s or '')
ap=argparse.ArgumentParser(); ap.add_argument('--yes',action='store_true'); a=ap.parse_args()
qs,sig=store.load_for_update()
# exact duplicates
g=collections.defaultdict(list)
for q in qs:
    g[(q.type,norm(q.stem),tuple(norm(o.text) for o in q.options))].append(q)
dup=0; groups=0
for k,v in g.items():
    if len(v)>1:
        groups+=1; tag=f'D{groups:03d}'
        for q in v:
            q.meta['duplicate_group']=tag; q.meta['duplicate_size']=len(v); dup+=1
# lowres
low=0; widths={}
for q in qs:
    ws=[]
    for f in q.figures:
        p=IMG/f.id
        if p.is_file():
            try:
                with Image.open(p) as im: ws.append(im.width)
            except Exception: pass
    if ws and min(ws)<400:
        q.meta['figure_low_res']=True; q.meta['figure_min_width']=min(ws); low+=1
    else:
        q.meta.pop('figure_low_res',None); q.meta.pop('figure_min_width',None)
print('duplicate questions',dup,'groups',groups,'lowres',low)
if a.yes:
    store.rewrite_all(qs,based_on=sig); print('written')
else: print('dry run')
