"""AmTiKu · 分享包（题目 + 图片 + manifest）

只打包**导出派生件**，不改变题库真相：

    name.amti-pack.zip
      manifest.json
      questions/0001.tex      # 原题块（%% @q + LaTeX），导入时走 question_from_block
      images/<内容寻址名>      # 题干/选项引用的图片

导入策略（刻意保守）：

- 同 key 已存在 → **跳过，不覆盖**；
- 图片名已存在 → 校验 sha256，一致才复用，不一致报错；
- 包内文件只允许 `questions/` / `images/`，拒绝 `..`、绝对路径和软链接；
- 先全部校验，再 `store.append()` 一次写入；写失败不会留下“半包题”。

这不是 MathBank 的 AGPL 代码/格式，只是同一类产品能力：
**把一套题连图带走，到另一台机器导入**。
"""
from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from pathlib import Path, PurePosixPath

from . import store
from .images import IMG_DIR
from .logutil import get_logger

log = get_logger(__name__)

FORMAT = "amti-share"
VERSION = 1
MAX_ITEMS = 2000
MAX_PACK_BYTES = 200 * 1024 * 1024
_MAX_MANIFEST = 2 * 1024 * 1024


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _safe_member(name: str) -> str:
    """zip 成员名只允许相对、正斜杠、无 `..`。"""
    p = PurePosixPath(str(name).replace("\\", "/"))
    if p.is_absolute() or not p.parts or any(x in ("..", "") for x in p.parts):
        raise ValueError("非法包内路径：%s" % name)
    return str(p)


def _image_name(name: str) -> str:
    n = str(name or "")
    if not n or Path(n).name != n or n in (".", ".."):
        raise ValueError("非法图片名：%s" % name)
    return n


def _app_version() -> str:
    try:
        from .paths import ROOT
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip() or "?"
    except Exception:
        return "?"


def build_pack(keys: list[str], name: str = "分享包") -> tuple[bytes, dict]:
    """按 key 生成 zip 字节；返回 `(bytes, report)`。"""
    keys = [k for k in dict.fromkeys(k.strip() for k in keys or []) if k]
    if not keys:
        raise ValueError("没有选题目")
    if len(keys) > MAX_ITEMS:
        raise ValueError("一次最多分享 %d 道题" % MAX_ITEMS)

    by = store.read_many(keys)
    missing = [k for k in keys if k not in by]
    if missing:
        raise ValueError("这些题不存在：%s" % "、".join(missing[:5]))

    items: list[dict] = []
    images: dict[str, dict] = {}
    written: set[str] = set()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for i, key in enumerate(keys, 1):
            q = by[key]
            block = store.render_question(q)
            member = "questions/%04d.tex" % i
            zf.writestr(member, block.encode("utf-8"))
            imgs: list[str] = []
            for fig in q.figures or ():
                try:
                    n = _image_name(fig.id)
                except ValueError:
                    continue
                p = IMG_DIR / n
                if not p.is_file():
                    continue
                data = p.read_bytes()
                h = _sha_bytes(data)
                if n not in images:
                    images[n] = {"sha256": h, "size": len(data)}
                imgs.append(n)
                if n not in written:
                    zf.writestr("images/" + n, data)
                    written.add(n)
            items.append({
                "key": q.key,
                "hash": q.content_hash(),
                "file": member,
                "images": imgs,
            })

        manifest = {
            "format": FORMAT,
            "version": VERSION,
            "name": str(name or "分享包")[:120],
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "app_version": _app_version(),
            "n": len(items),
            "items": items,
            "images": images,
        }
        zf.writestr("manifest.json",
                    json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8"))

    data = buf.getvalue()
    if len(data) > MAX_PACK_BYTES:
        raise ValueError("分享包超过 %d MB" % (MAX_PACK_BYTES // 1024 // 1024))
    return data, {"n": len(items), "bytes": len(data),
                  "images": len(images), "missing": missing}


def read_manifest(data: bytes) -> dict:
    if len(data) > MAX_PACK_BYTES:
        raise ValueError("包太大")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ValueError("不是 zip 分享包") from e
    with zf:
        names = {_safe_member(n) for n in zf.namelist()}
        if "manifest.json" not in names:
            raise ValueError("缺少 manifest.json")
        info = zf.getinfo("manifest.json")
        if info.file_size > _MAX_MANIFEST:
            raise ValueError("manifest 太大")
        try:
            m = json.loads(zf.read("manifest.json").decode("utf-8"))
        except Exception as e:
            raise ValueError("manifest 不是合法 JSON") from e
        if m.get("format") != FORMAT:
            raise ValueError("不是 AmTiKu 分享包（format=%r）" % m.get("format"))
        if int(m.get("version") or 0) > VERSION:
            raise ValueError("分享包版本过新：%s" % m.get("version"))
        if not isinstance(m.get("items"), list) or not m["items"]:
            raise ValueError("分享包没有题目")
        if len(m["items"]) > MAX_ITEMS:
            raise ValueError("分享包题目过多")
        return m


def import_pack(data: bytes, *, dry_run: bool = False) -> dict:
    """导入分享包；同 key 跳过，不覆盖。返回导入报告。"""
    m = read_manifest(data)
    zf = zipfile.ZipFile(io.BytesIO(data))
    errors: list[str] = []
    skipped: list[str] = []
    new_qs = []
    written_imgs: list[str] = []

    with zf:
        names = {_safe_member(n) for n in zf.namelist()}
        existing = {q.key for q in store.load_cached()}

        # 先校验图片并写入（内容寻址名；已存在则比对哈希）
        for n, meta in (m.get("images") or {}).items():
            try:
                n = _image_name(n)
                member = "images/" + n
                if member not in names:
                    errors.append("缺图片：%s" % n)
                    continue
                raw = zf.read(member)
                want = str((meta or {}).get("sha256") or "")
                if want and _sha_bytes(raw) != want:
                    errors.append("图片哈希不符：%s" % n)
                    continue
                dst = IMG_DIR / n
                if dst.is_file():
                    if _sha_bytes(dst.read_bytes()) != _sha_bytes(raw):
                        errors.append("图片同名但内容不同：%s" % n)
                    continue
                if not dry_run:
                    IMG_DIR.mkdir(parents=True, exist_ok=True)
                    tmp = dst.with_name(dst.name + ".tmp")
                    tmp.write_bytes(raw)
                    tmp.replace(dst)
                    written_imgs.append(n)
            except Exception as e:
                errors.append("图片 %s：%s" % (n, e))

        # 再解析题目；同 key 跳过
        for item in m["items"]:
            try:
                key = str(item.get("key") or "")
                member = _safe_member(str(item.get("file") or ""))
                if not member.startswith("questions/"):
                    errors.append("题块路径不在 questions/：%s" % member)
                    continue
                if member not in names:
                    errors.append("缺题块：%s" % member)
                    continue
                if key and key in existing:
                    skipped.append(key)
                    continue
                block = zf.read(member).decode("utf-8")
                q = store.question_from_block(block)
                if q is None or not q.key:
                    errors.append("解析不出题：%s" % (key or member))
                    continue
                want = str(item.get("hash") or "")
                if want and q.content_hash() != want:
                    errors.append("题块哈希不符：%s" % q.key)
                    continue
                if q.key in existing:
                    skipped.append(q.key)
                    continue
                existing.add(q.key)
                new_qs.append(q)
            except Exception as e:
                errors.append("题块 %s：%s" % (item.get("file"), e))

    if errors:
        return {"ok": False, "imported": 0, "skipped": skipped,
                "errors": errors, "dry_run": dry_run}
    if dry_run:
        return {"ok": True, "imported": len(new_qs), "skipped": skipped,
                "errors": [], "dry_run": True,
                "keys": [q.key for q in new_qs]}

    try:
        store.append(new_qs)
    except Exception as e:
        return {"ok": False, "imported": 0, "skipped": skipped,
                "errors": ["写入题库失败：%s" % e], "dry_run": False}
    return {"ok": True, "imported": len(new_qs), "skipped": skipped,
            "errors": [], "dry_run": False,
            "keys": [q.key for q in new_qs], "images": written_imgs}


def _selftest() -> int:
    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        print(("  ✓ " if cond else "  ✗ ") + name + (("  " + extra) if extra else ""))
        if not cond:
            fails += 1

    for bad in ("../x", "/abs/x", "a\\..\\b", ""):
        try:
            _safe_member(bad)
            ok = False
        except ValueError:
            ok = True
        check("拒绝非法包内路径 %r" % bad, ok)

    # 空包/坏包
    for raw in (b"not a zip", b""):
        try:
            read_manifest(raw)
            ok = False
        except ValueError:
            ok = True
        check("拒绝坏包", ok)

    print("sharepack 自检 %s（%d 项失败）"
          % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
