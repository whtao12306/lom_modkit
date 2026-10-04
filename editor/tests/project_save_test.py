# -*- coding: utf-8 -*-
"""文件夹项目保存行为回归测试。

覆盖两个用户反馈：
  #1 打开文件夹后，「保存」不该再让你选位置——新章节直接存回项目文件夹；
  #4 保存单个章节不能把「上次打开」降级成那个文件，否则下次启动只会打开单文件。

用法（在 editor/ 目录下）：
    .venv/Scripts/python tests/project_save_test.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

EDITOR_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EDITOR_DIR))

from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402  # type: ignore[reportMissingImports]

import main  # noqa: E402
import models  # noqa: E402


def _fresh(ed):
    win = main.MainWindow(ed, False)
    win._prompt_on_discard = True  # 允许写入会话偏好（下面会换成内存字典，不落盘）
    win.show()
    QApplication.processEvents()
    return win


def _make_story(folder: Path, sid: str) -> Path:
    story = models.new_story(sid, None)
    story["nodes"].append(models.new_node("end", "end1", None))
    path = folder / f"{sid}.json"
    path.write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
    return path


def _spy_prefs(win) -> dict:
    """把偏好读写换成内存字典，避免污染用户真实设置。"""
    prefs: dict = {}
    win.game_manager.save_pref = lambda k, v: prefs.__setitem__(k, v)
    win.game_manager.load_pref = lambda k, _p=prefs: _p.get(k)
    return prefs


def test_new_chapter_saves_into_folder(ed) -> None:
    """#1：文件夹项目里新建章节后保存，不弹框、直接落回项目文件夹。"""
    win = _fresh(ed)
    os.environ.pop("QT_QPA_PLATFORM", None)  # 让 _should_persist_session 为真
    prefs = _spy_prefs(win)
    calls = []
    orig = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = staticmethod(
        lambda *a, **k: (calls.append(1), ("", ""))[-1]
    )
    folder = Path(tempfile.mkdtemp())
    a, b = _make_story(folder, "a"), _make_story(folder, "b")
    try:
        win._load_story_paths([a, b], folder=folder)
        QApplication.processEvents()
        assert win._project_origin == "folder", win._project_origin
        assert prefs.get("last_open_kind") == "folder"

        # 已加载章节：保存写回原文件，不弹框
        assert win.save_story() is True
        assert calls == [], "已加载章节保存不应弹框"

        # 新建章节（无落盘路径）：保存也不该弹框，直接存进项目文件夹
        win._add_story_in_project()
        QApplication.processEvents()
        sid = win._current_id
        assert win.story_path is None, "新章节此时不应有路径"
        assert win.save_story() is True
        assert calls == [], f"新章节保存不应弹框，实际弹了 {len(calls)} 次"
        assert (folder / f"{sid}.json").is_file(), "新章节应落回项目文件夹"
        assert Path(win.story_path) == folder / f"{sid}.json"
    finally:
        QFileDialog.getSaveFileName = orig
        win.close()
    print("[#1 保存] 文件夹项目内保存不弹框、新章节落回项目文件夹")


def test_save_keeps_folder_session(ed) -> None:
    """#4：保存章节后「上次打开」仍是文件夹，不被降级成单文件。"""
    win = _fresh(ed)
    os.environ.pop("QT_QPA_PLATFORM", None)
    prefs = _spy_prefs(win)
    folder = Path(tempfile.mkdtemp())
    a, b = _make_story(folder, "a"), _make_story(folder, "b")
    win._load_story_paths([a, b], folder=folder)
    QApplication.processEvents()
    assert prefs.get("last_open_kind") == "folder"
    assert win.save_story() is True
    QApplication.processEvents()
    assert win._project_origin == "folder", "保存不应改变项目来源"
    assert prefs.get("last_open_kind") == "folder", (
        f"保存后会话被降级：{prefs.get('last_open_kind')}"
    )
    assert prefs.get("last_open_path") == str(folder.resolve()), (
        f"保存后 last_open_path 被改成了单文件：{prefs.get('last_open_path')}"
    )
    win.close()
    print("[#4 会话] 保存章节后仍记住文件夹，不降级为单文件")


def test_restore_story_with_siblings_opens_folder(ed) -> None:
    """启动自愈：历史遗留的单文件记录，若同目录还有别的剧情 → 按文件夹打开。"""
    win = _fresh(ed)
    os.environ.pop("QT_QPA_PLATFORM", None)
    folder = Path(tempfile.mkdtemp())
    _make_story(folder, "a")
    b = _make_story(folder, "b")
    prefs = _spy_prefs(win)
    prefs["last_open_kind"] = "story"  # 模拟被降级后的旧记录
    prefs["last_open_path"] = str(b.resolve())
    assert win.restore_last_project() is True
    QApplication.processEvents()
    assert win._project_origin == "folder", f"应自愈为文件夹，实际 {win._project_origin}"
    assert len(win._stories) == 2, f"应载入同目录两个剧情，实际 {sorted(win._stories)}"
    assert prefs.get("last_open_kind") == "folder", "自愈后应把记录改回 folder"
    win.close()
    print("[自愈] 单文件记录 + 同目录多剧情 → 自动按文件夹打开")


def test_deleted_chapter_path_not_inherited(ed) -> None:
    """删除章节后必须清掉它的落盘路径，否则新建同名章节会覆盖掉那个文件。"""
    win = _fresh(ed)
    win._prompt_on_discard = False  # 跳过删除确认弹框
    _spy_prefs(win)
    folder = Path(tempfile.mkdtemp())
    main_file = _make_story(folder, "main")
    _make_story(folder, "b")
    win._load_story_paths([main_file, folder / "b.json"], folder=folder)
    QApplication.processEvents()
    title_before = json.loads(main_file.read_text(encoding="utf-8")).get("title")

    win._current_id = "main"
    win._refresh_all()
    QApplication.processEvents()
    win._delete_story_in_project()
    QApplication.processEvents()
    assert "main" not in win._story_paths, "删除章节后仍残留落盘路径"

    win._add_story_in_project()  # make_story_id 会复用 "main"
    QApplication.processEvents()
    assert win._current_id == "main"
    assert win.story_path is None, "新章节不应继承已删章节的路径"
    # 目标文件已存在且不属本项目 → 拒绝静默覆盖，退回「另存为」
    calls = []
    orig = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = staticmethod(
        lambda *a, **k: (calls.append(1), ("", ""))[-1]
    )
    try:
        win.save_story()
    finally:
        QFileDialog.getSaveFileName = orig
    assert calls, "同名文件已存在时应弹框让用户决定，不要静默覆盖"
    assert json.loads(main_file.read_text(encoding="utf-8")).get("title") == title_before, (
        "已删除章节的文件不得被新章节覆盖"
    )
    win.close()
    print("[章节删除] 落盘路径不残留，新章节不会覆盖已删文件")


def test_unsafe_story_id_never_escapes_folder(ed) -> None:
    """章节 id 未经校验，非法 id 不得让保存写到项目目录之外。"""
    win = _fresh(ed)
    os.environ.pop("QT_QPA_PLATFORM", None)
    _spy_prefs(win)
    folder = Path(tempfile.mkdtemp())
    story = models.new_story("x", None)
    story["id"] = "../../escape"  # 故意用路径穿越型 id
    story["nodes"].append(models.new_node("end", "end1", None))
    bad = folder / "x.json"
    bad.write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
    win._load_story_paths([bad], folder=folder)
    QApplication.processEvents()
    win.story_path = None  # 模拟「这一章还没有落盘路径」

    assert win._infer_save_path() is None, "非法 id 不应推断出保存路径"
    calls = []
    orig = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = staticmethod(
        lambda *a, **k: (calls.append(1), ("", ""))[-1]
    )
    try:
        win.save_story()
    finally:
        QFileDialog.getSaveFileName = orig
    assert calls, "非法 id 应退回「另存为」弹框，而不是静默写盘"
    assert not (folder.parent / "escape.json").exists(), "文件写到了项目目录之外"
    win.close()
    print("[路径安全] 非法章节 id 不会写到项目目录之外")


def test_folder_project_bundles_assets(ed) -> None:
    """文件夹项目：assets/ 必须在 mod 根下，不能因为源是目录就找错层级。"""
    win = _fresh(ed)
    _spy_prefs(win)
    root = Path(tempfile.mkdtemp())
    (root / "assets").mkdir()
    (root / "assets" / "bg.png").write_bytes(b"x")
    (root / "story").mkdir()
    story = models.new_story("a", None)
    story["nodes"].append(models.new_node("end", "end1", None))
    f = root / "story" / "a.json"
    f.write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
    win._load_story_paths([f], folder=root)  # 选的是 mod 根（目录）
    QApplication.processEvents()
    assert win._project_bundled_assets() == ["assets/bg.png"], (
        f"文件夹项目应收集到 assets/，实际 {win._project_bundled_assets()}"
    )
    win.close()
    print("[导出资产] 文件夹项目能找到 mod 根下的 assets/")


def main_fn() -> int:
    app = QApplication([])
    ed, _fb = models.load_editor_data(main.PROJECT_ROOT)
    test_new_chapter_saves_into_folder(ed)
    test_save_keeps_folder_session(ed)
    test_restore_story_with_siblings_opens_folder(ed)
    test_deleted_chapter_path_not_inherited(ed)
    test_unsafe_story_id_never_escapes_folder(ed)
    test_folder_project_bundles_assets(ed)
    print("\nproject_save_test 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main_fn())
