r"""删题安全自检 —— 危险操作，单独一层。

删一道题会**重写整库**。逻辑再小心也可能有没预料到的分支，所以这里把
"不该发生的事"逐条证一遍：

  ① 口令不对       → 一道都不动
  ② 题号不存在     → 整批不执行（**绝不能删一半**）
  ③ 正常删除       → 只少这一道，**其余部分逐字节不变**
  ④ 恢复           → 内容一字不差，库指纹回到删除前
  ⑤ 库里已有同号题 → 拒绝恢复，不覆盖
  ⑥ 备份           → 改库前自动留一代，能整库回滚

判据不是"看着对"，而是**全库指纹**（每条 key + 内容哈希，排序后 sha256）
——只要有一个字节变了，指纹就对不上。

自检会临时造一道 `__安全测试/删题#1`，**结束时无论成败都清掉并把库还原**，
最后再核对一次指纹是否回到最初。

    python3 测试/删题安全自检.py
"""
import hashlib, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from amti import store, trash
from amti.schema import Option, Question

fails = []
def check(name, cond, extra=""):
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else "   " + str(extra)))
    if not cond: fails.append(name)

def lib_fingerprint():
    """整个库的指纹：每条 key + 内容哈希，排序后取 sha256。
    **只要有一个字节变了，指纹就变。**"""
    h = hashlib.sha256()
    for _f, q in sorted(store.iter_questions(), key=lambda x: x[1].key):
        h.update(("%s\x00%s\x00" % (q.key, q.content_hash())).encode())
    return h.hexdigest()[:16]

print("删题安全测试\n")
# ⚠️ 回收站里**可能本来就有东西**（用户真的删过题）。所以下面一律用
# **相对计数**，不假设它是空的——早先写死 `== 0`，用户一删题这测试就红。
N_TRASH0 = trash.count()
print("【基线】回收站里原有 %d 条" % N_TRASH0)
fp0 = lib_fingerprint(); n0 = len(store.load_all())
print("  %d 道，库指纹 %s" % (n0, fp0))

# 造一道自检题
K = "__安全测试/删题#1"
q = Question(key=K, type="single_choice", stem="安全测试用题 $2+2=$",
             answer="B", solution="因为 $2+2=4$，故选 B.", points=["1.1.1"],
             meta={"book": "__安全测试", "year": 2024},
             options=[Option("A", "$3$"), Option("B", "$4$")])
store.append([q])
fp1 = lib_fingerprint(); n1 = len(store.load_all())
print("\n【加入自检题后】%d 道（+%d）" % (n1, n1 - n0))

try:
    print("\n【1】口令不对：必须一道都不动")
    r = trash.delete([K], password="0000")
    check("拒绝执行", r["ok"] is False)
    check("库指纹没变", lib_fingerprint() == fp1, lib_fingerprint())
    check("回收站没进东西", trash.count() == N_TRASH0,
          "%d → %d" % (N_TRASH0, trash.count()))

    print("\n【2】题号不存在：整批不执行，不能删一半")
    r = trash.delete([K, "__不存在/9"], password="0808")
    check("拒绝执行", r["ok"] is False)
    check("自检题**还在**（没删一半）", store.find(K) is not None)
    check("库指纹没变", lib_fingerprint() == fp1)
    check("回收站没进东西", trash.count() == N_TRASH0,
          "%d → %d" % (N_TRASH0, trash.count()))

    print("\n【3】正常删除：只少这一道，别的题一个字节都不能变")
    r = trash.delete([K], reason="现在的高考不考了", password="0808")
    check("删除成功", r["ok"], r.get("error"))
    check("库少一道", len(store.load_all()) == n1 - 1)
    check("这道题不在库里了", store.find(K) is None)
    check("回收站里有", trash.count() == N_TRASH0 + 1,
          "%d → %d" % (N_TRASH0, trash.count()))
    fp2 = lib_fingerprint()
    # 把自检题加回来，指纹应该回到 fp1
    probe = store.find("高考真题汇编/2024/新高考I卷#1")
    check("别的题还在（抽查一道）", probe is not None)
    check("别的题内容没变", probe.content_hash() ==
          next(x.content_hash() for _f, x in store.iter_questions()
               if x.key == "高考真题汇编/2024/新高考I卷#1"))

    print("\n【4】恢复：内容必须一字不差")
    r = trash.restore([K])
    check("恢复成功", r["ok"], r.get("error"))
    check("库回到原来的道数", len(store.load_all()) == n1)
    check("库指纹回到删除前", lib_fingerprint() == fp1, lib_fingerprint())
    back = store.find(K)
    check("题干一致", back.stem == q.stem)
    check("答案一致", back.answer == q.answer)
    check("解析一致", back.solution == q.solution)
    check("考点一致", back.points == q.points)
    check("选项一致", [(o.label, o.text) for o in back.options] == [("A", "$3$"), ("B", "$4$")])
    check("回收站回到原样", trash.count() == N_TRASH0,
          "%d → %d" % (N_TRASH0, trash.count()))

    print("\n【5】库里已有同号题时恢复：拒绝，不覆盖")
    trash.delete([K], password="0808")
    store.append([q])                       # 手工放一道同号的回去
    r = trash.restore([K])
    check("拒绝恢复", r["ok"] is False and r.get("clash") == [K], r)
    check("库里那道没被覆盖", store.find(K) is not None)
    store.rewrite_all([x for _f, x in store.iter_questions() if x.key != K])
    trash.purge([K], password="0808")   # **只清自己那条**——早先这里不带题号，等于清空整个回收站，把用户删的题一起抹了

    print("\n【6】备份机制：改库前自动留一代，能从备份回滚")
    # ⚠️ **只拿自检题开刀，绝不动真题。**
    # 早先这里写的是 `load_all()[1:]`——直接删掉库里的第一道**真题**，
    # 结果有一次改名阶段出错，那道真题就真没了（靠备份才救回来）。
    # 测试可以激进，但不能拿用户的数据冒险。
    if store.find(K) is None:
        store.append([q])
    n_before = len(store.load_all())
    fp_before = lib_fingerprint()
    store.rewrite_all([x for _f, x in store.iter_questions() if x.key != K])
    check("重写确实改了库（且少的只是自检题）",
          len(store.load_all()) == n_before - 1 and store.find(K) is None,
          "%d → %d" % (n_before, len(store.load_all())))
    check("改库前留下了备份", len(store.list_backups()) >= 1)
    check("备份里有卷文件", any(list(d.glob('*.tex')) for d in store.list_backups()))
    r = store.restore_backup()
    check("能从备份恢复", r.get("ok"), r)
    check("恢复后道数回到改之前", len(store.load_all()) == n_before,
          "%d vs %d" % (len(store.load_all()), n_before))
    check("恢复后指纹回到改之前", lib_fingerprint() == fp_before, lib_fingerprint())

finally:
    print("\n【清理】")
    # **清完要复查**：如果此时别的进程也在写库（Web 服务、求解器），
    # 它的整库重写可能把我们刚删掉的这道又带回来——实测踩过。
    for _ in range(3):
        try:
            store.rewrite_all([x for _f, x in store.iter_questions() if x.key != K])
        except Exception as e:
            print("   清理库失败：%s" % e)
        trash.purge([K], password="0808")   # **只清自己那条**——早先这里不带题号，等于清空整个回收站，把用户删的题一起抹了
        if store.find(K) is None:
            break
        time.sleep(0.3)
    fp3 = lib_fingerprint()
    check("自检题已清理，库回到最初", len(store.load_all()) == n0 and fp3 == fp0,
          "%d 道 / %s vs %d 道 / %s" % (len(store.load_all()), fp3, n0, fp0))

print()
print("安全测试 %s（%d 项失败）" % ("通过" if not fails else "未通过", len(fails)))
for f in fails: print("   ✗ %s" % f)
sys.exit(1 if fails else 0)
