# -*- coding: utf-8 -*-
"""编辑器易用性增强的回归测试：死亡编号递增 / 登场快捷退场 / 多选上下移动。

用法（在 editor/ 目录下）：
    .venv/Scripts/python tests/editor_ux_test.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

EDITOR_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EDITOR_DIR))

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402  # type: ignore[reportMissingImports]

import main  # noqa: E402
import models  # noqa: E402

SCHEMA = models.STORY_SCHEMA


def _fresh(ed):
    win = main.MainWindow(ed, False)
    win._prompt_on_discard = False
    win.show()
    QApplication.processEvents()
    return win


def _load(win, nodes):
    win._install_project(
        {"main": {"story_schema": SCHEMA, "id": "main", "start": nodes[0]["id"], "nodes": nodes}},
        {"main": None}, "main", "untitled", None,
    )
    QApplication.processEvents()


def test_death_id_auto_increment(ed) -> None:
    win = _fresh(ed)
    _load(win, [{"id": "n0", "type": "music", "name": "a"}])
    win._select_node_index(0)
    for _ in range(3):
        win._add_node("death")
        QApplication.processEvents()
    ids = [n.get("death_id") for n in win.story["nodes"] if n["type"] == "death"]
    assert ids == ["900001", "900002", "900003"], f"死亡编号应自增，实际 {ids}"
    # 再试 next_death_id 对非 900001 起点的处理
    win.story["nodes"].append({"id": "d9", "type": "death", "death_id": "910200"})
    assert models.next_death_id(win.story) == "910201", "应在最大值 +1"
    win.close()
    print("[死亡编号] 新增死亡画面自动递增 900001→900002→900003")


def test_show_exit_button(ed) -> None:
    win = _fresh(ed)
    show = models.new_node("show", "show1", ed)
    show["character"] = "artist1"
    win.form.set_node(show)
    QApplication.processEvents()
    buttons = [b for b in win.form.findChildren(QPushButton) if b.text() == "退场"]
    assert len(buttons) == 1, f"登场步骤应有「退场」按钮，实际 {len(buttons)}"
    buttons[0].click()
    QApplication.processEvents()
    hides = [n for n in win.story["nodes"] if n["type"] == "hide"]
    assert hides and hides[0].get("character") == "artist1", (
        f"点退场应添加当前人物的退场步骤，实际 {hides}"
    )
    # 非 show 节点不应有退场按钮
    music = models.new_node("music", "m1", ed)
    win.form.set_node(music)
    QApplication.processEvents()
    assert not [b for b in win.form.findChildren(QPushButton) if b.text() == "退场"], (
        "非登场步骤不应有退场按钮"
    )
    win.close()
    print("[快捷退场] 登场步骤「退场」按钮正确追加退场步骤")


def test_multi_move(ed) -> None:
    win = _fresh(ed)
    nodes = [{"id": f"n{i}", "type": "music", "name": "a"} for i in range(5)]
    _load(win, nodes)

    def ids():
        return [n["id"] for n in win.story["nodes"]]

    # 选中 1、3（先清掉默认选中的第 0 步）→ 上移
    win.node_list.clearSelection()
    for i in (1, 3):
        win.node_list.item(win._list_row_for_node_index(i)).setSelected(True)
    QApplication.processEvents()
    win._move_node(-1)
    QApplication.processEvents()
    assert ids() == ["n1", "n0", "n3", "n2", "n4"], f"上移结果异常：{ids()}"
    assert win._selected_node_indexes() == [0, 2], (
        f"上移后应保持选中 [0,2]，实际 {win._selected_node_indexes()}"
    )

    # 已到顶（第 0 步被选中）→ 再上移不动
    win._move_node(-1)
    QApplication.processEvents()
    assert ids() == ["n1", "n0", "n3", "n2", "n4"], "顶到边界不应再移动"

    # 连续块 {1,2,3} 整体下移，块内顺序不变
    win.node_list.clearSelection()
    for i in (1, 2, 3):
        win.node_list.item(win._list_row_for_node_index(i)).setSelected(True)
    QApplication.processEvents()
    win._move_node(1)
    QApplication.processEvents()
    assert ids() == ["n1", "n4", "n0", "n3", "n2"], f"整块下移结果异常：{ids()}"
    assert win._selected_node_indexes() == [2, 3, 4], (
        f"整块下移后应保持选中 [2,3,4]，实际 {win._selected_node_indexes()}"
    )
    win.close()
    print("[多选移动] 散点/连续块 上移下移 + 选区保持 均正确")


def main_fn() -> int:
    app = QApplication([])
    ed, _fb = models.load_editor_data(main.PROJECT_ROOT)
    test_death_id_auto_increment(ed)
    test_show_exit_button(ed)
    test_multi_move(ed)
    print("\neditor_ux_test 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main_fn())
