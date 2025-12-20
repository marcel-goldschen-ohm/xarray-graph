""" Tree view for a `KeyValueTreeModel` with drag-and-drop, context menu, and mouse wheel expand/collapse.

TODO:
- edit numpy 1d/2d arrays in a table?
"""

from __future__ import annotations
from copy import deepcopy
import numpy as np
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph.tree import KeyValueTreeItem, KeyValueTreeModel, TreeView


class KeyValueTreeView(TreeView):

    _copied_key_value_map = {}

    def __init__(self, *args, **kwargs) -> None:
        TreeView.__init__(self, *args, **kwargs)

        self._cut_icon = qta.icon('mdi.content-cut')
        self._copy_icon = qta.icon('mdi.content-copy')
        self._paste_icon = qta.icon('mdi.content-paste')
    
    def customContextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu:
        model: KeyValueTreeModel = self.model()
        menu = QMenu(self)

        # item that was clicked on
        item: KeyValueTreeItem = model.itemFromIndex(index)
        
        # selection
        has_selection: bool = self.selectionModel().hasSelection()
        if self.selectionMode() in [QAbstractItemView.SelectionMode.ContiguousSelection, QAbstractItemView.SelectionMode.ExtendedSelection, QAbstractItemView.SelectionMode.MultiSelection]:
            menu.addSeparator()
            menu.addAction(self._selectAllAction)
            menu.addAction(self._clearSelectionAction)
        
        # cut/copy/paste
        has_copy: bool = self.hasCopy()
        menu.addSeparator()
        menu.addAction(QAction('Cut', parent=menu, icon=self._cut_icon, iconVisibleInMenu=True, triggered=lambda checked: self.cutSelection(), enabled=has_selection))
        menu.addAction(QAction('Copy', parent=menu, icon=self._copy_icon, iconVisibleInMenu=True, triggered=lambda checked: self.copySelection(), enabled=has_selection))
        menu.addAction(QAction('Paste', parent=menu, icon=self._paste_icon, iconVisibleInMenu=True, triggered=lambda checked, parent_item=item: self.pasteCopy(parent_item), enabled=has_copy))
        
        # remove item(s)
        menu.addSeparator()
        menu.addAction(QAction('Remove', parent=menu, triggered=lambda checked: self.removeSelectedItems(), enabled=has_selection))
        
        # insert new item
        menu.addSeparator()
        if item is model.rootItem():
            menu.addAction(QAction('Add New', parent=menu, triggered=lambda checked, parent_item=item, row=len(item.children): self.insertNew(parent_item, row)))
        else:
            menu.addAction(QAction('Insert New', parent=menu, triggered=lambda checked, parent_item=item.parent, row=item.row: self.insertNew(parent_item, row)))
        
        # expand/collapse
        menu.addSeparator()
        menu.addAction(self._expandAllAction)
        menu.addAction(self._collapseAllAction)
        if model.columnCount() > 1:
            menu.addAction(self._resizeAllColumnsToContentsAction)
            menu.addAction(self._showAllAction)

        # refresh
        menu.addSeparator()
        menu.addAction(self._refreshAction)
        
        return menu
    
    def toJson(self, items: list[KeyValueTreeItem]):
        pass
    
    def cutSelection(self) -> None:
        self.copySelection()
        self.removeSelectedItems(ask=False)
    
    def copySelection(self) -> None:
        items: list[KeyValueTreeItem] = self.selectedItems()
        if not items:
            return
        # only copy the branch roots (this already includes the descendents)
        items = KeyValueTreeModel._branchRootItemsOnly(items)
        # copy the values in each branch root subtree
        copied_key_value_map: dict = {}
        for item in items:
            key = KeyValueTreeModel.unique_name(item.key, list(copied_key_value_map.keys()))
            copied_key_value_map[key] = deepcopy(item.value)
        KeyValueTreeView._copied_key_value_map = copied_key_value_map
    
    def pasteCopy(self, parent_item: KeyValueTreeItem = None) -> None:
        model: KeyValueTreeModel = self.model()
        if not model:
            return
        copied_key_value_map = KeyValueTreeView._copied_key_value_map
        if not copied_key_value_map:
            return
        if parent_item is None:
            items = self.selectedItems()
            if not items:
                return
            parent_item = items[0]
            if not parent_item.is_map or len(items) > 1:
                parent_widget: QWidget = self
                title = 'Invalid Paste'
                text = f'Must select a single key:value map item in which to paste.'
                QMessageBox.warning(parent_widget, title, text)
                return
        # paste items
        name_item_map: dict[str, KeyValueTreeItem] = {key: KeyValueTreeItem(deepcopy(value)) for key, value in copied_key_value_map.items()}
        row: int = len(parent_item.children)
        model.insertItems(name_item_map, row, parent_item)
    
    def hasCopy(self) -> bool:
        if KeyValueTreeView._copied_key_value_map:
            return True
        return False
    
    def insertNew(self, parent_item: KeyValueTreeItem, row: int) -> None:
        model: KeyValueTreeModel = self.model()
        names = [item.name for item in parent_item.children]
        name = model.unique_name('New', names)
        new_item = KeyValueTreeItem('')
        model.insertItems({name: new_item}, row, parent_item)


def test_live():

    data = {
        'a': 1,
        'b': [4, 8, (1, 5.5234985270827504823702, True, 'good'), 5, 7, 99, True, False, 'hi', 'bye'],
        'c': {
            'me': 'hi',
            3: 67,
            'd': {
                'e': np.float32(3.14),
                'f': 'ya!',
                'g': np.int16(5),
            },
        },
        '1d': np.array([1, 2, 3]),
        'nd': np.array([[1, 2, 3], [4, 5, 6]]),
    }

    app = QApplication()

    root = KeyValueTreeItem(data)

    model = KeyValueTreeModel()
    model.setTypesColumnVisible(True)
    model.setRootItem(root)

    view = KeyValueTreeView()
    view.setModel(model)
    view.show()
    view.resize(QSize(800, 800))
    view.move(QPoint(100, 100))
    view.showAll()
    view.raise_()

    from copy import deepcopy
    data2 = deepcopy(data)

    root2 = KeyValueTreeItem(data2)

    model2 = KeyValueTreeModel()
    model2.setTypesColumnVisible(True)
    model2.setRootItem(root2)

    view2 = KeyValueTreeView()
    view2.setModel(model2)
    view2.show()
    view2.resize(QSize(800, 800))
    view2.move(QPoint(950, 100))
    view2.showAll()
    view2.raise_()

    app.exec()

    # print(model.rootItem())
    print(data)

if __name__ == '__main__':
    test_live()
