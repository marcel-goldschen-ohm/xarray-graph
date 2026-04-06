""" Tree view for a `KeyValueTreeModel` with drag-and-drop, context menu, and mouse wheel expand/collapse.

TODO:
- edit numpy 1d/2d arrays in a table?
"""

from __future__ import annotations
import numpy as np
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph.tree import KeyValueTreeItem, KeyValueTreeModel, TreeView


class KeyValueTreeView(TreeView):
    """ Tree view for a `KeyValueTreeModel` with drag-and-drop, context menu, and mouse wheel expand/collapse.
    """

    def __init__(self, *args, **kwargs) -> None:
        TreeView.__init__(self, *args, **kwargs)

        self._cut_icon = qta.icon('mdi.content-cut')
        self._copy_icon = qta.icon('mdi.content-copy')
        self._paste_icon = qta.icon('mdi.content-paste')

        self._showTypeColumnAction = QAction(
            text='Show Type Column',
            icon=qta.icon('fa6s.info'),
            iconVisibleInMenu=True,
            checkable=True,
            checked=False,
            toolTip='Show data type column in the tree view. Uncheck to hide column.',
            triggered=lambda checked: self._updateModelFromViewOptions(),
        )
    
    def treeData(self) -> dict | list:
        """ Get the root key:value map.
        """
        model: KeyValueTreeModel = self.model()
        return model.treeData()
    
    def setTreeData(self, data: dict | list) -> None:
        """ Set the root key:value map.
        """
        model: KeyValueTreeModel = self.model()
        if model is None:
            model = KeyValueTreeModel()
            model.setTreeData(data)
            self.setModel(model)
        else:
            self.storeViewState()
            model.setTreeData(data)
            self.restoreViewState()
    
    def setModel(self, model: KeyValueTreeModel, updateViewOptionsFromModel: bool = True) -> None:
        super().setModel(model)
        if updateViewOptionsFromModel:
            self._updateViewOptionsFromModel()
        else:
            self._updateModelFromViewOptions()

    def _updateViewOptionsFromModel(self):
        model: KeyValueTreeModel = self.model()
        self._showTypeColumnAction.blockSignals(True)
        self._showTypeColumnAction.setChecked(model.isTypesColumnVisible())
        self._showTypeColumnAction.blockSignals(False)

    def _updateModelFromViewOptions(self):
        model: KeyValueTreeModel = self.model()
        self.storeViewState()
        model.setTypesColumnVisible(self._showTypeColumnAction.isChecked())
        self.restoreViewState()
    
    def customContextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu:
        model: KeyValueTreeModel = self.model()
        menu = QMenu(self)

        # item that was clicked on
        item: KeyValueTreeItem = model.itemFromIndex(index)
        
        # selection
        has_selection: bool = self.selectionModel().hasSelection()
        self._clearSelectionAction.setEnabled(has_selection)
        if self.selectionMode() in [QAbstractItemView.SelectionMode.ContiguousSelection, QAbstractItemView.SelectionMode.ExtendedSelection, QAbstractItemView.SelectionMode.MultiSelection]:
            menu.addSeparator()
            menu.addAction(self._selectAllAction)
            menu.addAction(self._clearSelectionAction)
        
        # cut/copy/paste
        has_copy: bool = self.hasCopy()
        self._cutSelectionAction.setEnabled(has_selection)
        self._copySelectionAction.setEnabled(has_selection)
        self._pasteAction.setEnabled(has_copy)
        menu.addSeparator()
        menu.addAction(self._cutSelectionAction)
        menu.addAction(self._copySelectionAction)
        menu.addAction(self._pasteAction)

        # remove item(s)
        self._removeSelectedAction.setEnabled(has_selection)
        menu.addSeparator()
        menu.addAction(self._removeSelectedAction)
        
        # insert new item
        menu.addSeparator()
        if item is not model.rootItem():
            menu.addAction(QAction(
                text='Insert New',
                parent=menu,
                triggered=lambda checked, parent_item=item.parent, row=item.siblingIndex(): self.insertNew(parent_item, row),
            ))
        if item.isContainer():
            menu.addAction(QAction(
                text='Append New Child',
                parent=menu,
                triggered=lambda checked, parent_item=item, row=len(item.children): self.insertNew(parent_item, row),
            ))
        
        # expand/collapse
        menu.addSeparator()
        menu.addAction(self._expandAllAction)
        menu.addAction(self._collapseAllAction)
        if model.columnCount() > 1:
            menu.addAction(self._resizeAllColumnsToContentsAction)
            menu.addAction(self._showAllAction)
        
        # options
        menu.addSeparator()
        menu.addAction(self._showTypeColumnAction)

        # refresh
        menu.addSeparator()
        menu.addAction(self._refreshAction)
        
        return menu
    
    def pasteCopy(self, parent_item: KeyValueTreeItem = None, row: int = None) -> None:
        if not self.hasCopy():
            return
        model: KeyValueTreeModel = self.model()
        if not model:
            return
        if parent_item is None:
            selected_items = self.selectedItems()
            if selected_items:
                parent_item = selected_items[0]
            else:
                parent_item = model.rootItem()
        if row is None or row == -1:
            row = len(parent_item.children)
        # ----------------------------------------------------------
        # KeyValueTreeView specific logic
        if not parent_item.isContainer() and not parent_item.isRoot():
            row = parent_item.siblingIndex()
            parent_item = parent_item.parent
        # ----------------------------------------------------------
        items_to_paste = [item.copy() for item in TreeView._copied_items]
        model.insertItems(items_to_paste, row, parent_item)
    
    def insertNew(self, parent_item: KeyValueTreeItem, row: int = None) -> None:
        model: KeyValueTreeModel = self.model()
        if not model:
            return
        if parent_item is None:
            selected_items = self.selectedItems()
            if selected_items:
                parent_item = selected_items[0]
            else:
                parent_item = model.rootItem()
        if row is None or row == -1:
            row = len(parent_item.children)
        if not parent_item.isContainer() and not parent_item.isRoot():
            row = parent_item.siblingIndex()
            parent_item = parent_item.parent
        
        names = [item.name() for item in parent_item.children]
        name = model.uniqueName('New', names)
        new_item = KeyValueTreeItem(name, None)
        model.insertItems([new_item], row, parent_item)


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

    root = KeyValueTreeItem(None, data)
    root.updateSubtree()

    model = KeyValueTreeModel()
    model.setTypesColumnVisible(True)
    model.setRootItem(root)

    view = KeyValueTreeView()
    view.setModel(model)
    view.show()
    view.resize(QSize(800, 800))
    view.move(QPoint(50, 50))
    view.showAll()
    view.raise_()

    from copy import deepcopy
    data2 = deepcopy(data)

    root2 = KeyValueTreeItem(None, data2)
    root2.updateSubtree()

    model2 = KeyValueTreeModel()
    model2.setTypesColumnVisible(True)
    model2.setRootItem(root2)

    view2 = KeyValueTreeView()
    view2.setModel(model2)
    view2.show()
    view2.resize(QSize(800, 800))
    view2.move(QPoint(900, 50))
    view2.showAll()
    view2.raise_()

    app.exec()

    # print(model.rootItem())
    print(data)

if __name__ == '__main__':
    test_live()
