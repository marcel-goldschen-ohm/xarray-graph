""" Utils for an abstract item tree model/view.
"""
from __future__ import annotations

from xarray_graph.tree.AbstractTreeItem import AbstractTreeItem


def orderedItems[TreeItem: AbstractTreeItem](items: list[TreeItem], order='depth-first') -> list[TreeItem]:
    """ Returns the input items ordered according to their position in the tree.
    """
    if not items:
        return []
    root = items[0].root()  # assume all items are in the same tree
    ordered_items: list[TreeItem] = []
    if order == 'depth-first':
        for item in root.subtree_depth_first():
            if item in items:
                ordered_items.append(item)
    elif order == 'breadth-first':
        for item in root.subtree_breadth_first():
            if item in items:
                ordered_items.append(item)
    return ordered_items


def itemBlocks[TreeItem: AbstractTreeItem](items: list[TreeItem]) -> list[list[TreeItem]]:
    """ Group items by parent and contiguous rows.

    Each block can be input to removeRows() or moveRows() in the model.
    Blocks are ordered depth-first. Typically you should remove/move blocks in reverse depth-first order to ensure insertion row indices remain valid after handling each block.
    """
    # order items depth-first so that it is easier to group them into blocks
    items = orderedItems(items, order='depth-first')

    # group items into blocks by parent and contiguous rows
    blocks = [[items[0]]]
    for item in items[1:]:
        added_to_block = False
        for block in blocks:
            if item.parent is block[0].parent:
                if item.siblingIndex() == block[-1].siblingIndex() + 1:
                    block.append(item)
                else:
                    blocks.append([item])
                added_to_block = True
                break
        if not added_to_block:
            blocks.append([item])
    return blocks


def branchRootItemsOnly[TreeItem: AbstractTreeItem](items: list[TreeItem]) -> list[TreeItem]:
    """ Discard items that are descendents of other items.
    """
    items = items.copy()
    for item in tuple(items):
        for other_item in items:
            if other_item is item:
                continue
            if item.hasAncestor(other_item):
                # item is a descendent of other_item
                items.remove(item)
                break
    return items


def allItemsAndTheirDescendents[TreeItem: AbstractTreeItem](items: list[TreeItem]) -> list[TreeItem]:
    """ Returns the input items along with all of their descendents.
    """
    if not items:
        return []
    all_items: list[TreeItem] = []
    for item in items:
        for descendant in item.subtree_depth_first():
            if descendant not in all_items:
                all_items.append(descendant)
    return all_items


def uniqueName(name: str, names: list[str], unique_counter_start: int = 1) -> str:
    """ Return name_1, or name_2, etc. until a unique name is found that does not exist in names.

    This is useful for managing trees that require unique paths.
    """
    if name not in names:
        return name
    base_name = name
    i = unique_counter_start
    name = f'{base_name}_{i}'
    while name in names:
        i += 1
        name = f'{base_name}_{i}'
    return name


def popupWarningDialog(title: str, text: str, system_warn: bool = True) -> None:
    from qtpy.QtWidgets import QApplication, QMessageBox
    focus_widget = QApplication.focusWidget()
    QMessageBox.warning(focus_widget, title, text)
    if system_warn:
        from warnings import warn
        warn(text)
