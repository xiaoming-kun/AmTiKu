"""AmTiKu · 分卷存储

唯一真相是分卷的 LaTeX 文件（`题目/001.tex` …，每卷 ≤ 5000 题）。

**append-only 是这里唯一的硬规则**：

  * 新题只追加到最后一卷
  * 活卷满 5000 题 → 开新卷，原卷冻结
  * 永不重排、永不插入、永不物理删除
  * 删除只在索引里标记，文件里留墓碑注释（行号因此保持稳定）

文件格式（每题两块）：

    %% @q {"key":"…","hash":"…","type":"…",…}      ← 机读，完整字段
    \\begin{question}                               ← 人读，exam-zh 标准
    …
    \\end{question}

两块由同一个 IR 生成，**不可能不一致**——旧项目主文件和语料各存一份，
就出过不一致。
"""
from __future__ import annotations

import json
import os
import time
import re
from contextlib import contextmanager
from pathlib import Path

from .latex_ir import parse_question, split_questions
from .schema import Question, from_dict, to_dict

from amti.logutil import get_logger

log = get_logger(__name__)

PKG = Path(__file__).resolve().parent.parent
TOPIC_DIR = PKG / "题目"
PER_VOLUME = 5000

META_LINE = "%% @q "
META_RE = re.compile(r"^%% @q (\{.*\})\s*$", re.M)
GRAVE_MARK = "%% @gone"


# ── 卷的定位 ──────────────────────────────────────────────────────────

def volume_path(no: int) -> Path:
    return TOPIC_DIR / f"{no:03d}.tex"


def existing_volumes() -> list[Path]:
    return sorted(TOPIC_DIR.glob("[0-9][0-9][0-9].tex")) if TOPIC_DIR.exists() else []


def active_volume() -> tuple[Path, int]:
    """返回 (活卷路径, 卷号)。没有卷就返回 1 号（尚未创建）。"""
    vols = existing_volumes()
    if not vols:
        return volume_path(1), 1
    last = vols[-1]
    return last, int(last.stem)


# ── 写 ────────────────────────────────────────────────────────────────

def render_question(q: Question) -> str:
    """把一道题渲染成「元数据行 + LaTeX」两块。

    LaTeX 部分**只由 IR 生成**——本模块是唯一产出主文件内容的地方。
    """
    from .render_tex import question_to_tex      # 延迟导入，避免循环
    head = META_LINE + json.dumps(to_dict(q), ensure_ascii=False, sort_keys=True)
    return head + "\n" + question_to_tex(q).rstrip() + "\n"


def append(questions: list[Question], *, dry_run: bool = False) -> list[str]:
    r"""把题目追加到活卷。返回写入日志。

    **只追加**：本函数不读、不重写已有内容，只在文件末尾写下新块。
    活卷写满 PER_VOLUME 题后自动开新卷。
    """
    log: list[str] = []
    if not questions:
        return log

    path, no = active_volume()
    count = vol_count(path)

    for q in questions:
        if count >= PER_VOLUME:
            no += 1
            path = volume_path(no)
            count = 0
            log.append(f"开新卷 {path.name}")
        block = render_question(q)
        if not dry_run:
            TOPIC_DIR.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write("\n" + block)
        count += 1
        log.append(f"追加 {path.name}  {q.key}  hash={q.content_hash()}")
    return log


def vol_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in META_RE.finditer(path.read_text(encoding="utf-8")))


# ── 备份（危险写操作的安全网） ────────────────────────────────────────
#
# 删题、批量改题这类操作会**重写整库**。逻辑再小心也可能有没预料到的分支，
# 所以每次重写之前，把上一代卷文件原样留一份：
#
#     题目/备份/20260913_120530/001.tex …
#
# 一卷 10 MB 上下、整库 36 MB，留 3 代也就 100 MB——**比丢数据的代价便宜太多**。
# `store.restore_backup()` / `python3 amti.py backup --restore` 能把它放回去。

BACKUP_DIR = TOPIC_DIR / "备份"
KEEP_BACKUPS = 3


def backup_dir_for(stamp: str) -> Path:
    return BACKUP_DIR / stamp


def list_backups() -> list[Path]:
    """历次备份，**新的在前**。"""
    if not BACKUP_DIR.is_dir():
        return []
    ds = [d for d in BACKUP_DIR.iterdir() if d.is_dir() and d.name[:4].isdigit()]
    return sorted(ds, key=lambda d: d.name, reverse=True)


def _backup_volumes() -> Path | None:
    r"""把当前卷文件整份复制到 `题目/备份/<时间戳>/`。返回备份目录。

    没东西可备（第一次建库）就返回 None。
    """
    vols = existing_volumes()
    if not vols:
        return None
    stamp = time.strftime("%Y%m%d_%H%M%S")
    d = backup_dir_for(stamp)
    # 同一秒内连着写两次：复用同一个目录，别覆盖也别堆一堆
    if d.exists():
        n = 1
        while (BACKUP_DIR / ("%s_%d" % (stamp, n))).exists():
            n += 1
        d = BACKUP_DIR / ("%s_%d" % (stamp, n))
    d.mkdir(parents=True, exist_ok=True)
    for p in vols:
        (d / p.name).write_bytes(p.read_bytes())
    # 只留最近 KEEP_BACKUPS 代，免得越堆越多
    for old in list_backups()[KEEP_BACKUPS:]:
        for f in old.iterdir():
            f.unlink(missing_ok=True)
        old.rmdir()
    return d


def restore_backup(stamp: str = "") -> dict:
    r"""把某一代备份放回去。`stamp` 留空就用最近一代。"""
    bs = list_backups()
    if not bs:
        return {"ok": False, "error": "没有备份可恢复"}
    d = None
    if stamp:
        d = next((b for b in bs if b.name == stamp or b.name.startswith(stamp)), None)
    else:
        d = bs[0]
    if d is None:
        return {"ok": False, "error": "没有这一代备份：%s" % stamp}
    srcs = sorted(d.glob("*.tex"))
    if not srcs:
        return {"ok": False, "error": "这一代备份是空的：%s" % d.name}
    for p in srcs:
        (TOPIC_DIR / p.name).write_bytes(p.read_bytes())
    # 备份里没有的卷号（比如现在是 4 卷、备份是 2 卷）要删掉，
    # 否则旧卷残留会让库凭空多出一截
    keep_no = set()
    for p in srcs:
        try:
            keep_no.add(int(p.stem))
        except ValueError:
            pass
    for p in existing_volumes():
        try:
            if int(p.stem) not in keep_no:
                p.unlink()
        except ValueError:
            pass
    return {"ok": True, "from": d.name, "volumes": len(srcs),
            "questions": sum(vol_count(TOPIC_DIR / p.name) for p in srcs)}


# ── 写锁（跨进程） ────────────────────────────────────────────────────
#
# 库是**多个进程共用**的：后台求解器在写、`amti.py` 在写、Web 服务也在写。
# 两个写入方撞在一起会怎样，实测见过两种：
#
#   · **抢同一个 `.tmp`**：临时文件名原先写死成 `001.tex.tmp`，
#     两个进程同时写就互相把对方的临时文件改名走，
#     报 `FileNotFoundError: 001.tex.tmp -> 001.tex`，
#     而且**库已经被改了一半**。
#   · **互相覆盖**：A 读全库、B 读全库、A 写、B 写 —— A 的改动没了。
#
# 所以所有重写操作都要先拿这把锁。用 `fcntl.flock`（macOS/Linux 都有），
# 拿不到就等——写库是短操作，等一会儿比写坏强。
LOCK_FILE = TOPIC_DIR / ".写锁"


def _lock_try(f) -> bool:
    r"""试拿一次锁，成不成都不等。**跨平台**：POSIX 用 `fcntl.flock`，Windows 用 `msvcrt.locking`。

    Windows 没有 `fcntl` —— 不加这条分支，Windows 上一写库就 `ModuleNotFoundError`。
    """
    if os.name == "nt":
        import msvcrt
        try:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    import fcntl
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _lock_release(f) -> None:
    r"""放锁。与 `_lock_try` 配对。"""
    if os.name == "nt":
        import msvcrt
        try:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        return
    import fcntl
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


@contextmanager
def lib_lock(timeout: float = 120.0):
    r"""独占写锁。**所有会改库的操作都必须先拿它。**（macOS/Linux/Windows 通用）"""
    TOPIC_DIR.mkdir(parents=True, exist_ok=True)
    f = open(LOCK_FILE, "w")
    t0 = time.time()
    try:
        while not _lock_try(f):
            if time.time() - t0 > timeout:
                raise TimeoutError("等写锁超过 %.0f 秒（另一个进程在改库？）" % timeout)
            time.sleep(0.1)
        yield
    finally:
        try:
            _lock_release(f)
        finally:
            f.close()


def _tmp_path(path: Path) -> Path:
    r"""临时文件名**必须带上进程号**。

    写死成 `001.tex.tmp` 的话，两个写库的进程会抢同一个文件——
    一个刚写完、另一个把它改名走，前一个就 `FileNotFoundError`，
    而库里已经是改了一半的状态。实测踩过。
    """
    return path.with_name("%s.tmp.%d" % (path.name, os.getpid()))


def rewrite_all(questions: list[Question], *, dry_run: bool = False) -> dict:
    r"""**改若干道题并保存的正确入口。**

    按 `PER_VOLUME` 重新分卷写回，并删掉多余的卷文件。
    传进来的列表是**全库**（`load_all()` 的结果）就对了——
    这正是它比 `rewrite_volume` 安全的地方：分卷由它负责。

    为什么要这样：`rewrite_volume(1, load_all())` 会把所有卷的题
    都写进第 1 卷，而其它卷文件还在，`load_all()` 一读就重复。
    这个错误不会报错、不会崩，只会让库**悄悄变大**——最坏的那种 bug。
    """
    # 同一个 key 只留一份（后出现的覆盖先出现的）
    uniq: dict[str, Question] = {}
    for q in questions:
        uniq[q.key] = q
    ordered = list(uniq.values())

    _last_dup_dropped[0] = len(questions) - len(ordered)
    with lib_lock():
        return _rewrite_all_locked(ordered, dry_run=dry_run)


# 去重掉了几条（包装函数算好放这儿，正体只读它）
_last_dup_dropped = [0]


def _rewrite_all_locked(ordered: list[Question], *, dry_run: bool = False) -> dict:
    r"""`rewrite_all` 的正体。**调用方必须已经持有写锁。**"""
    chunks = [ordered[i:i + PER_VOLUME]
              for i in range(0, len(ordered), PER_VOLUME)] or [[]]
    ordered_keys = [q.key for q in ordered]

    # ⚠️ **两阶段写盘**，不要一个卷一个卷地 `rewrite_volume`。
    #
    # 为什么：`rewrite_volume` 有一道**跨卷重复护栏**——写第 i 卷前先看
    # 这些 key 是不是已经躺在别的卷里。日常防误用靠它，但**整库重排时
    # 它必然误报**：只要题目**数量变了**（删一道、加一道），分卷边界就
    # 右移一位，原本属于第 2 卷的题要挪进第 1 卷；写第 1 卷的那一刻，
    # 它还在第 2 卷里——护栏看到的就是"跨卷重复"。
    #
    # 实测踩过：删一道题 → `rewrite_all` 抛 ValueError → 题没删掉，
    # 而回收站里已经写了记录（顺序也不对），于是出现了"库里和回收站里都有"。
    #
    # 两阶段就没有这个窗口：① 全部先写 `.tmp`，正式卷文件一个都不动；
    # ② 全部写完再一起改名。改名是原子的，中途崩了旧文件也还在。
    if dry_run:
        return {"volumes": [rewrite_volume(i, c, dry_run=True, verify_cross=False)
                            for i, c in enumerate(chunks, start=1)],
                "count": len(ordered), "volumes_n": len(chunks)}

    TOPIC_DIR.mkdir(parents=True, exist_ok=True)

    # ── 第 1 层安全网：**先把内容写好并验过，再碰正式文件** ──
    #
    # 每一卷写成 `.tmp` 之后**重新解析一遍**，核对：
    #   · 解析回来的 key 集合和预期**一模一样**（不多不少）
    #   · 没有重复 key
    # 任何一条不符就**当场抛错，正式卷文件一个字节都没动**。
    # 这一步挡的是"渲染/写入逻辑有 bug，把库写坏"——最要命的那种。
    tmps: list[Path] = []
    for i, chunk in enumerate(chunks, start=1):
        body = "\n".join(render_question(q) for q in chunk)
        tmp = _tmp_path(volume_path(i))
        tmp.write_text(body + "\n", encoding="utf-8")

        back = [q for q in (question_from_block(b)
                            for b in split_questions(tmp.read_text(encoding="utf-8")))
                if q is not None and q.key]
        want_keys = [q.key for q in chunk]
        got_keys = [q.key for q in back]
        if len(set(got_keys)) != len(got_keys):
            tmp.unlink(missing_ok=True)
            raise ValueError("写第 %d 卷时出现重复 key，已中止（正式文件未改动）" % i)
        if set(want_keys) != set(got_keys):
            tmp.unlink(missing_ok=True)
            miss = sorted(set(want_keys) - set(got_keys))[:3]
            extra = sorted(set(got_keys) - set(want_keys))[:3]
            raise ValueError(
                "写第 %d 卷后回读对不上，已中止（正式文件未改动）：少 %s，多 %s"
                % (i, miss, extra))
        tmps.append(tmp)

    # ── 第 2 层安全网：**改名前留一份上一代** ──
    _backup_volumes()

    reports = []
    for i, chunk in enumerate(chunks, start=1):
        reports.append(rewrite_volume(i, chunk, dry_run=True, verify_cross=False))
    for i, tmp in enumerate(tmps, start=1):
        tmp.replace(volume_path(i))
    for i, rep in enumerate(reports, start=1):
        rep["volume"] = volume_path(i).name

    # ── 第 3 层安全网：**改完再从磁盘验一遍** ──
    #
    # 万一改名阶段出了意外（磁盘满、被打断），这里能立刻发现。
    # 发现不对就把上一代拷回来——**宁可回到改之前，也不留半坏的库**。
    try:
        on_disk = [q.key for _f, q in iter_questions()]
        if len(set(on_disk)) != len(on_disk) or set(on_disk) != set(ordered_keys):
            raise ValueError("回读的 key 集合与预期不符")
    except Exception as e:
        restore_backup()
        raise ValueError("写盘后校验失败，已回滚到改之前：%s" % e)

    # 删掉不再需要的卷文件（比如从 2 卷缩回 1 卷）
    if not dry_run:
        for extra in sorted(TOPIC_DIR.glob("*.tex")):
            if ".tmp" in extra.name:
                continue
            try:
                no = int(extra.stem)
            except ValueError:
                continue
            if no > len(chunks):
                extra.unlink()

    return {
        "volumes": len(chunks),
        "count": len(ordered),
        # 注：`ordered` 已经去过重，调用方传进来的总数在包装函数里
        "duplicates_dropped": _last_dup_dropped[0],
        "changed": [k for r in reports for k in r["changed"]],
        "reports": reports,
    }


def rewrite_volume(no: int, questions: list[Question], *,
                   dry_run: bool = False, verify_cross: bool = True) -> dict:
    r"""**整卷重写——只给 MIGRATE 用。日常录入请用 `append`。**

    `append` 只追加，这是它最大的价值：程序没有任何改写存量数据的可能。
    但一次性迁移（比如把 `\includegraphics{旧名}` 换成内容寻址名）必须能改
    已有内容，所以留这一个口子。为了不被误用：

      * 名字直接叫 rewrite，调用点一眼能看出是迁移不是录入
      * 返回前后指纹对照，**改了几道、改了哪些**都报出来
      * 先写临时文件再原子替换，中途失败不会留半个文件

    ⚠️ **这个函数不会替你分卷。** 给它的列表原样写进第 `no` 卷。
    传 `load_all()`（跨多卷）进来就会把别的卷的题也复制一份，
    而原卷还在——**整库瞬间翻倍**。实测踩过：库涨到 22,650 道、
    重复条目 14,120 条，就是 `rewrite_volume(1, load_all())` 干的。

    **要改若干道题并保存，用 `rewrite_all()`，不要直接调这个。**
    """
    if len(questions) > PER_VOLUME:
        raise ValueError(
            "rewrite_volume(%d, …) 收到 %d 道题，超过单卷上限 %d。"
            "你多半传了跨卷的列表——请改用 rewrite_all()。"
            % (no, len(questions), PER_VOLUME))
    path = volume_path(no)
    old: dict[str, str] = {}
    if path.exists():
        for block in split_questions(path.read_text(encoding="utf-8")):
            if GRAVE_MARK in block:
                continue
            q = question_from_block(block)      # 与 iter_questions 同一条路
            if q is not None and q.key:
                old[q.key] = q.content_hash()

    new_keys = {q.key for q in questions}

    # ⚠️ **跨卷重复护栏。** 写第 `no` 卷之前，先看这些 key 是不是已经
    # 躺在**别的卷**里了——是的话写完就会整库重复，而 `load_all()` 不会报错。
    # 这是把「静默损坏」变成「当场失败」的那道闸。
    #
    # `verify_cross=False` 是给 `rewrite_all` 用的：整库重排时**跨卷挪动
    # 本来就该发生**（题目总数一变，分卷边界就移），这时候护栏必然误报。
    # 生产路径上只有 `rewrite_all` 会传 False，而且它两阶段写盘、
    # 正式文件在改名之前一个都不动——所以那道闸的用意并没有丢。
    clash: set[str] = set()
    for p in ([] if not verify_cross else existing_volumes()):
        if p == path:
            continue
        for block in split_questions(p.read_text(encoding="utf-8")):
            if GRAVE_MARK in block:
                continue
            m = META_RE.search(block)
            if m:
                try:
                    k = json.loads(m.group(1)).get("key", "")
                except ValueError:
                    k = ""
                if k in new_keys:
                    clash.add(k)
    if clash:
        raise ValueError(
            "拒绝写入 %s：其中 %d 个 key 已经存在于别的卷（例：%s）。"
            "直接把跨卷列表交给 rewrite_volume 会让整库重复，"
            "请改用 rewrite_all()。"
            % (path.name, len(clash), sorted(clash)[0]))

    report = {
        "volume": path.name,
        "count": len(questions),
        "changed": [q.key for q in questions
                    if q.key in old and old[q.key] != q.content_hash()],
        "added": [k for k in new_keys if k not in old],
        "removed": [k for k in old if k not in new_keys],
    }
    if dry_run:
        return report

    TOPIC_DIR.mkdir(parents=True, exist_ok=True)
    body = "\n".join(render_question(q) for q in questions)
    # 写盘这几步拿锁：**求解器就走这条路**，它可能在后台一直写，
    # 不锁的话会和界面上删题、`amti.py` 迁移撞在一起。
    with lib_lock():
        tmp = _tmp_path(path)
        try:
            tmp.write_text(body + "\n", encoding="utf-8")
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)      # 改名成功就没了；失败也别留垃圾
    return report


# ── 读 ────────────────────────────────────────────────────────────────

def question_from_block(block: str) -> Question | None:
    r"""一个题块 → Question。**「块 → 题」的唯一入口。**

    `iter_questions` 和 `rewrite_volume` 都必须走这里。早先两处各写一遍，
    结果 `rewrite_volume` 漏了「题型以元数据为准」这条，把一道多选题的旧指纹
    按单选题算，于是报出一道假的内容变化——**迁移工具自己误报，比不报更糟**。
    """
    q = parse_question(block)
    if q is None:
        return None
    m = META_RE.search(block)
    if m:
        d = json.loads(m.group(1))
        q.key = d.get("key", "") or q.key
        q.points = d.get("points") or []
        # **题型以元数据为准**：`question` 环境里既有单选也有填空，
        # 光看环境推不出来（没有选项又没星号时二义）。
        # LaTeX 环境由题型生成，两者是否一致可以单独校验。
        if d.get("type"):
            q.type = d["type"]
        for k, v in (d.get("meta") or {}).items():
            q.meta.setdefault(k, v)
    return q


def iter_questions():
    r"""遍历所有题目。

    **LaTeX 正文是字段的真相**（题干/选项/答案/解析/题型/配图），
    元数据行只补 LaTeX 表达不了的东西（key / 来源 / 标签）。

    这样直接编辑 `.tex` 正文是**有效**的，而且会被 `diff()` 抓到——
    早先只读元数据 JSON，等于文件里有两份真相，手改正文不生效
    （实测：改了题干，`diff` 报"内容变化 0"，等于漏报）。
    """
    for path in existing_volumes():
        text = path.read_text(encoding="utf-8")
        for block in split_questions(text):
            if GRAVE_MARK in block:
                continue                        # 墓碑：索引里标了删除
            q = question_from_block(block)
            if q is not None:
                yield path.name, q


def duplicate_keys() -> dict[str, int]:
    r"""全库重复的 key → 出现次数。

    **重复是静默的**：`load_all()` 会老老实实返回两份，
    界面、导出、统计全都翻倍，但不报任何错。
    实测踩过：库从 8,530 涨到 22,650，重复条目 14,120 条，
    根因是 `rewrite_volume(1, load_all())` 把多卷内容重复写进第 1 卷。

    所以这件事必须有**看得见**的检查（`amti.py verify` 会调它）。
    """
    seen: dict[str, int] = {}
    for _f, q in iter_questions():
        seen[q.key] = seen.get(q.key, 0) + 1
    return {k: n for k, n in seen.items() if n > 1}


def roundtrip_problems(questions=None, *, sample: int = 400) -> list[dict]:
    r"""**往返一致性**：题目写出去再读回来，内容指纹必须一个字节都不变。

    这是在防一类很隐蔽的 bug：**写库路径上混进了"渲染期才算的改动"**。

    `store.render_question` 是拿 `render_tex.question_to_tex` 把题目序列化回
    `.tex` 的——也就是说**渲染函数同时是写库函数**。一旦往渲染里塞了
    "出卷子时才该做的事"（比如把 TikZ 换成图片、把公式改个写法），
    每写一次库就悄悄改一次数据。

    实测踩过：给 `question_to_tex` 加了「TikZ→预渲染图片」的替换，
    结果一次批量迁移就把 **236 道题的题干**改写成了 `\includegraphics`，
    还把 TikZ 源码弄丢了（重新解析时被当成位图）。

    这个检查就是那种 bug 的照妖镜：**改没改数据，写一遍再读一遍就知道**。
    """
    qs = questions if questions is not None else load_all()
    if sample and len(qs) > sample:
        step = max(1, len(qs) // sample)
        qs = qs[::step][:sample]
    bad = []
    for q in qs:
        before = q.content_hash()
        text = render_question(q)
        # ⚠️ **整段传进去**：`split_questions` 是按 `%% @q` 元数据行切的，
        # 只传 LaTeX 正文会切出 0 块（第一次就踩了这个坑，500 道全报"读不回来"）。
        blocks = list(split_questions(text))
        if not blocks:
            bad.append({"key": q.key, "why": "写出去读不回来"})
            continue
        back = question_from_block(blocks[0])
        if back is None:
            bad.append({"key": q.key, "why": "写出去读不回来"})
            continue
        after = back.content_hash()
        if after != before:
            bad.append({"key": q.key,
                        "why": "写一遍再读回来，指纹变了（%s → %s）" % (before, after)})
    return bad


def load_all() -> list[Question]:
    r"""读全部题。

    ⚠️ **不按 key 去重**——去重会把库里的结构问题盖住。
    要检查有没有重复，调 `duplicate_keys()`。
    要读一份干净的，用 `load_unique()`。
    """
    return [q for _f, q in iter_questions()]


# 全库缓存：**按卷文件的 mtime+size 失效**。
#
# 每读一次都要把 4 个卷文件解析成 17,554 个 Question，约 0.6 秒。
# 读接口每次都这么干，页面就卡。缓存键取「卷文件的修改时间+大小」——
# 只要文件没被写，内存里那份就还是对的；求解任务写盘后 mtime 变，
# 下一次请求自动重读。**不是定时过期，是写盘才失效**，不会读到旧数据。
_CACHE: dict = {"key": (), "qs": []}


def _vol_signature() -> tuple:
    sig = []
    for p in existing_volumes():
        try:
            st = p.stat()
            sig.append((p.name, st.st_mtime_ns, st.st_size))
        except OSError:
            pass
    return tuple(sig)


def load_cached() -> list[Question]:
    r"""读全库，**带缓存**。读接口用这个；写路径仍用 `load_all()`。

    写路径必须读最新的，所以不缓存——反正一次只有一道题在写。
    """
    sig = _vol_signature()
    if _CACHE["key"] != sig:
        _CACHE["qs"] = load_all()
        _CACHE["key"] = sig
    return _CACHE["qs"]


def cache_clear() -> None:
    _CACHE["key"] = ()
    _CACHE["qs"] = []


def load_unique() -> list[Question]:
    """读全部题，**同一个 key 只留最后一份**。改库前用它。"""
    uniq: dict[str, Question] = {}
    for _f, q in iter_questions():
        uniq[q.key] = q
    return list(uniq.values())


def find(key: str) -> Question | None:
    for _f, q in iter_questions():
        if q.key == key:
            return q
    return None


# ── 变更检测 ──────────────────────────────────────────────────────────

SNAPSHOT = PKG / "归档快照.json"


def snapshot() -> dict:
    """记录当前每道题的指纹。这是"存量有没有被改"的基线。

    除指纹外还记一份 `solved_at`——**求解器写库不算"规则动了存量"**，
    但光看指纹分不出来。有了求解时间就能在 `diff` 里把两类变化分开报。
    """
    rows = list(iter_questions())
    items = {q.key: q.content_hash() for _f, q in rows}
    solved = {q.key: ((q.meta or {}).get("solved_at") or "") for _f, q in rows}
    # 录入升级（界面点「用这份更新」）也记一笔——它**有意**改存量，
    # 不该和"规则偷偷动了数据"混在一个报警里。
    upgraded = {q.key: ((q.meta or {}).get("upgraded_at") or "") for _f, q in rows}
    # 界面补录（改答案/解析/题型）也记一笔——那是**人有意改的**，
    # 不该和"规则偷偷动了存量"混在一个报警里。
    edited = {q.key: ((q.meta or {}).get("edited_at") or "") for _f, q in rows}
    migrated = {q.key: ((q.meta or {}).get("migrated_at") or "") for _f, q in rows}
    data = {"questions": len(items), "fingerprints": items,
            "solved": solved, "upgraded": upgraded, "edited": edited,
            "migrated": migrated}
    SNAPSHOT.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True),
                        encoding="utf-8")
    return data


def load_snapshot() -> dict:
    if not SNAPSHOT.exists():
        return {}
    return json.loads(SNAPSHOT.read_text(encoding="utf-8")).get("fingerprints", {})


def load_snapshot_solved() -> dict:
    """基线里每道题的求解时间。老基线没有这一项就返回空表。"""
    if not SNAPSHOT.exists():
        return {}
    return json.loads(SNAPSHOT.read_text(encoding="utf-8")).get("solved", {})


def load_snapshot_migrated() -> dict:
    """基线里每道题的规则迁移时间。老基线没有这一项就返回空表。"""
    if not SNAPSHOT.exists():
        return {}
    return json.loads(SNAPSHOT.read_text(encoding="utf-8")).get("migrated", {})


def load_snapshot_edited() -> dict:
    """基线里每道题的界面补录时间。老基线没有这一项就返回空表。"""
    if not SNAPSHOT.exists():
        return {}
    return json.loads(SNAPSHOT.read_text(encoding="utf-8")).get("edited", {})


def load_snapshot_upgraded() -> dict:
    """基线里每道题的升级时间。老基线没有这一项就返回空表。"""
    if not SNAPSHOT.exists():
        return {}
    return json.loads(SNAPSHOT.read_text(encoding="utf-8")).get("upgraded", {})


def diff() -> dict:
    r"""对比基线：返回 {新增, 内容变化, 删除, 求解写入, 录入升级, 界面补录}。

    **这是给使用者的核心保证**——不靠承诺，靠这个输出：
    内容变化必须是 0（除非显式改过某道题，或者求解器刚写了解析）。

    `求解写入` 是 `内容变化` 里**求解时间比基线新**的那部分：那些是
    `amti.solve` 一道一道做出来的，属于正常产出，不该混进"规则动了
    存量"里一起报警。剩下的才是真正要人去查的。
    """
    base = load_snapshot()
    base_solved = load_snapshot_solved()
    base_upgraded = load_snapshot_upgraded()
    base_edited = load_snapshot_edited()
    base_migrated = load_snapshot_migrated()
    rows = list(iter_questions())
    now = {q.key: q.content_hash() for _f, q in rows}
    added = sorted(set(now) - set(base))
    removed = sorted(set(base) - set(now))
    changed = sorted(k for k in set(base) & set(now) if base[k] != now[k])

    cur_solved = {q.key: ((q.meta or {}).get("solved_at") or "") for _f, q in rows}
    cur_upgraded = {q.key: ((q.meta or {}).get("upgraded_at") or "") for _f, q in rows}
    solved_writes = sorted(k for k in changed
                           if cur_solved.get(k) and cur_solved[k] != base_solved.get(k))
    upgraded_writes = sorted(k for k in changed if k not in set(solved_writes)
                             and cur_upgraded.get(k)
                             and cur_upgraded[k] != base_upgraded.get(k))
    _taken = set(solved_writes) | set(upgraded_writes)
    cur_edited = {q.key: ((q.meta or {}).get("edited_at") or "") for _f, q in rows}
    edited_writes = sorted(k for k in changed if k not in _taken
                           and cur_edited.get(k)
                           and cur_edited[k] != base_edited.get(k))
    _taken2 = set(solved_writes) | set(upgraded_writes) | set(edited_writes)
    cur_migrated = {q.key: ((q.meta or {}).get("migrated_at") or "") for _f, q in rows}
    migrated_writes = sorted(k for k in changed if k not in _taken2
                             and cur_migrated.get(k)
                             and cur_migrated[k] != base_migrated.get(k))
    _sw = _taken2 | set(migrated_writes)
    changed = [k for k in changed if k not in _sw]
    # **有意删除**：进回收站的题，不该报成"数据丢了"。
    # 延迟导入，避免 store ←→ trash 循环依赖。
    try:
        from . import trash as _tr
        in_trash = _tr.keys()
    except Exception:
        log.debug("回收站列表不可用，本次对比不排除回收站题", exc_info=True)
        in_trash = set()
    trashed = [k for k in removed if k in in_trash]
    if trashed:
        removed = [k for k in removed if k not in in_trash]
    return {"新增": added, "内容变化": changed, "删除": removed,
            "求解写入": solved_writes, "录入升级": upgraded_writes,
            "界面补录": edited_writes, "规则迁移": migrated_writes,
            "回收站": trashed,
            "基线题数": len(base), "当前题数": len(now)}


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        vols = existing_volumes()
        total = sum(vol_count(p) for p in vols)
        print(f"卷数 {len(vols)}  题目 {total}")
        for p in vols:
            print(f"  {p.name}  {vol_count(p)} 题")
    elif cmd == "snapshot":
        d = snapshot()
        print(f"已存基线：{d['questions']} 道 → {SNAPSHOT.name}")
    elif cmd == "diff":
        d = diff()
        print(f"基线 {d['基线题数']} 道 → 当前 {d['当前题数']} 道")
        print(f"  新增      {len(d['新增'])}")
        print(f"  内容变化  {len(d['内容变化'])}   ← 这个必须是 0")
        print(f"  删除      {len(d['删除'])}")
        for k in d["内容变化"][:20]:
            print(f"      ✗ {k}")
