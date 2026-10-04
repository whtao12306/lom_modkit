# -*- coding: utf-8 -*-
"""编辑器易用性增强的回归测试：死亡编号递增 / 快捷退场 / 多选移动 / 批量删除 / 拖拽重排（含滚轮）。

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

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402  # type: ignore[reportMissingImports]

import main  # noqa: E402
import models  # noqa: E402

SCHEMA = models.STORY_SCHEMA


def _mouse(listw, event_type, pos, buttons=Qt.MouseButton.LeftButton) -> None:
    """向列表视口投递鼠标事件（QAbstractScrollArea 会把事件转给控件本体）。"""
    event = QMouseEvent(
        event_type,
        QPointF(pos),
        QPointF(listw.viewport().mapToGlobal(pos)),
        Qt.MouseButton.LeftButton,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(listw.viewport(), event)


def _wheel(listw, pos, angle_dy: int) -> None:
    event = QWheelEvent(
        QPointF(pos),
        QPointF(listw.viewport().mapToGlobal(pos)),
        QPoint(0, 0),
        QPoint(0, angle_dy),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(listw.viewport(), event)


def _row_point(listw, row: int, frac: float = 0.5) -> QPoint:
    rect = listw.visualItemRect(listw.item(row))
    y = rect.top() + max(1, int(rect.height() * frac))
    return QPoint(rect.center().x(), max(2, y))


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


def test_multi_drag_block(ed) -> None:
    """多选鼠标拖拽：整块搬移，块内相对顺序与选区都保持。"""
    win = _fresh(ed)
    nodes = [{"id": f"n{i}", "type": "music", "name": "a"} for i in range(6)]
    _load(win, nodes)

    def ids():
        return [n["id"] for n in win.story["nodes"]]

    # 选区采集（列表控件会把这一组下标随 drag 一起发出）
    win.node_list.clearSelection()
    for i in (2, 3):
        win.node_list.item(win._list_row_for_node_index(i)).setSelected(True)
    QApplication.processEvents()
    assert win.node_list._selected_step_indexes() == [2, 3], (
        f"选区采集异常：{win.node_list._selected_step_indexes()}"
    )

    # 模拟 dropEvent 发出的整块搬移信号：{2,3} 拖到插入点 5
    win._on_steps_moved([2, 3], 5)
    QApplication.processEvents()
    assert ids() == ["n0", "n1", "n4", "n2", "n3", "n5"], f"整块拖拽结果异常：{ids()}"
    assert win._selected_node_indexes() == [3, 4], (
        f"整块拖拽后应保持选中 [3,4]，实际 {win._selected_node_indexes()}"
    )

    # 撤销应能还原
    win._undo()
    QApplication.processEvents()
    assert ids() == ["n0", "n1", "n2", "n3", "n4", "n5"], "撤销未还原"

    # 原地放下不产生撤销记录
    before = len(win._undo_stack)
    win._on_steps_moved([0, 1], 1)
    QApplication.processEvents()
    assert len(win._undo_stack) == before, "原地放下不应产生撤销记录"

    # 旧的单下标调用仍兼容
    win._on_steps_moved(1, 0)
    QApplication.processEvents()
    assert ids()[0] == "n1", f"单下标拖拽兼容性异常：{ids()}"

    # 非连续选区整块搬到最前，相对顺序保持
    p = models.plan_reorder_nodes([{"id": f"n{i}"} for i in range(6)], [1, 3, 4], 0)
    assert p is not None and [n["id"] for n in p[0]] == ["n1", "n3", "n4", "n0", "n2", "n5"], (
        f"非连续整块搬移异常：{p}"
    )
    win.close()
    print("[多选拖拽] 整块搬移 + 选区保持 + 撤销 + 兼容单下标 均正确")


def test_batch_delete(ed) -> None:
    """多选状态下一次删除全部选中步骤（单条撤销记录，可整体还原）。"""
    win = _fresh(ed)
    nodes = [{"id": f"n{i}", "type": "music", "name": "a"} for i in range(6)]
    _load(win, nodes)

    def ids():
        return [n["id"] for n in win.story["nodes"]]

    win.node_list.clearSelection()
    for i in (1, 3, 4):
        win.node_list.item(win._list_row_for_node_index(i)).setSelected(True)
    QApplication.processEvents()
    win._delete_node()
    QApplication.processEvents()
    assert ids() == ["n0", "n2", "n5"], f"批量删除结果异常：{ids()}"

    win._undo()
    QApplication.processEvents()
    assert ids() == ["n0", "n1", "n2", "n3", "n4", "n5"], "批量删除应可整体撤销"

    # 单条删除仍照常
    win.node_list.clearSelection()
    win._select_node_index(2)
    QApplication.processEvents()
    win._delete_node()
    QApplication.processEvents()
    assert "n2" not in ids(), f"单条删除异常：{ids()}"
    win.close()
    print("[批量删除] 多选一次删除 + 整体撤销 + 单条删除 均正确")


def test_mouse_drag_reorder(ed) -> None:
    """自实现的鼠标拖拽：可用、可多选整块、单击不动、Esc 可取消。"""
    win = _fresh(ed)
    nodes = [{"id": f"n{i}", "type": "music", "name": "a"} for i in range(6)]
    _load(win, nodes)
    nl = win.node_list

    def ids():
        return [n["id"] for n in win.story["nodes"]]

    # 选中 n1、n2 后把它们拖到列表末尾
    nl.clearSelection()
    for i in (1, 2):
        nl.item(win._list_row_for_node_index(i)).setSelected(True)
    QApplication.processEvents()
    press = _row_point(nl, win._list_row_for_node_index(1))
    target = _row_point(nl, win._list_row_for_node_index(5), 0.95)
    _mouse(nl, QEvent.Type.MouseButtonPress, press)
    _mouse(nl, QEvent.Type.MouseMove, target)
    assert nl._dragging, "越过拖动阈值后应进入拖拽态"
    assert nl._drag_rows == [2, 3], f"应拖动整块选中行，实际 {nl._drag_rows}"
    _mouse(nl, QEvent.Type.MouseButtonRelease, target, buttons=Qt.MouseButton.NoButton)
    QApplication.processEvents()
    assert ids() == ["n0", "n3", "n4", "n5", "n1", "n2"], f"整块拖拽结果异常：{ids()}"

    # 单击（不移动）不应改动顺序
    before = ids()
    p = _row_point(nl, win._list_row_for_node_index(0))
    _mouse(nl, QEvent.Type.MouseButtonPress, p)
    _mouse(nl, QEvent.Type.MouseButtonRelease, p, buttons=Qt.MouseButton.NoButton)
    QApplication.processEvents()
    assert ids() == before, "单击不应移动步骤"

    # Esc 取消拖拽：顺序不变、退出拖拽态
    nl.clearSelection()
    nl.item(win._list_row_for_node_index(0)).setSelected(True)
    QApplication.processEvents()
    p0 = _row_point(nl, win._list_row_for_node_index(0))
    p1 = _row_point(nl, win._list_row_for_node_index(4))
    _mouse(nl, QEvent.Type.MouseButtonPress, p0)
    _mouse(nl, QEvent.Type.MouseMove, p1)
    assert nl._dragging
    QApplication.sendEvent(
        nl,
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
    )
    assert not nl._dragging, "Esc 应取消拖拽"
    _mouse(nl, QEvent.Type.MouseButtonRelease, p1, buttons=Qt.MouseButton.NoButton)
    QApplication.processEvents()
    assert ids() == before, "取消拖拽后顺序不应改变"
    win.close()
    print("[鼠标拖拽] 整块搬移 / 单击不动 / Esc 取消 均正确")


def test_wheel_scroll_during_drag(ed) -> None:
    """拖拽过程中滚轮必须能滚动列表（这是弃用 Qt 原生拖放的原因）。"""
    win = _fresh(ed)
    win.resize(1200, 600)
    QApplication.processEvents()
    nodes = [{"id": f"n{i}", "type": "music", "name": "a"} for i in range(40)]
    _load(win, nodes)
    nl = win.node_list
    bar = nl.verticalScrollBar()
    assert bar.maximum() > 0, "步骤多到足以滚动才谈得上验证"

    nl.clearSelection()
    row = win._list_row_for_node_index(3)
    nl.item(row).setSelected(True)
    QApplication.processEvents()
    press = _row_point(nl, row)
    target = _row_point(nl, row, 0.9)
    _mouse(nl, QEvent.Type.MouseButtonPress, press)
    _mouse(nl, QEvent.Type.MouseMove, target)
    assert nl._dragging
    before_value = bar.value()
    before_row = nl._drop_row

    _wheel(nl, target, -360)
    QApplication.processEvents()
    assert bar.value() != before_value, "拖拽中滚轮应能滚动列表"
    assert nl._drop_row != before_row, "滚动后落点应按光标重新定位"

    _mouse(nl, QEvent.Type.MouseButtonRelease, target, buttons=Qt.MouseButton.NoButton)
    QApplication.processEvents()
    assert not nl._dragging, "释放后应退出拖拽态"
    win.close()
    print("[拖拽滚动] 拖拽中滚轮可滚动、落点跟随光标 均正确")


def main_fn() -> int:
    app = QApplication([])
    ed, _fb = models.load_editor_data(main.PROJECT_ROOT)
    test_death_id_auto_increment(ed)
    test_show_exit_button(ed)
    test_multi_move(ed)
    test_batch_delete(ed)
    test_multi_drag_block(ed)
    test_mouse_drag_reorder(ed)
    test_wheel_scroll_during_drag(ed)
    print("\neditor_ux_test 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main_fn())
