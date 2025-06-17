""" Tree view of a AnnotationTreeModel with context menu and mouse wheel expand/collapse.
"""

from __future__ import annotations
from typing import Callable
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
from pyqt_ext.tree import AbstractTreeItem, TreeView
from xarray_graph.tree import AnnotationTreeModel


class AnnotationTreeView(TreeView):

    def __init__(self, parent: QObject = None) -> None:
        TreeView.__init__(self, parent)

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        # # these will appear in the item's context menu
        # self._itemContextMenuFunctions: list[tuple[str, Callable[[AbstractTreeItem]]]] = [
        #     ('Info', lambda item, self=self: self.popupItemInfo(item)),
        #     ('Attrs', lambda item, self=self: self.editItemAttrs(item)),
        #     ('Separator', None),
        #     ('Remove', lambda item, self=self: self.askToRemoveItem(item)),
        # ]
    
    def setDataTree(self, dt: xr.DataTree, paths: list[str] = None, key: str = 'annotations'):
        model: AnnotationTreeModel = self.model()
        if model is None:
            model = AnnotationTreeModel()
            TreeView.setModel(self, model)
        self.storeState()
        model.setDataTree(dt, paths=paths, key=key)
        self.restoreState()
        self._paths = paths
        self._key = key
    
    def refresh(self):
        model: AnnotationTreeModel = self.model()
        if model is None:
            return
        dt: xr.DataTree | None = model.dataTree()
        if dt is None:
            return
        paths = getattr(self, '_paths', None)
        key = getattr(self, '_key', 'annotations')
        self.setDataTree(dt, paths=paths, key=key)
    
    def setModel(self, model: AnnotationTreeModel):
        TreeView.setModel(self, model)
        self.refresh()
    
    def selectedAnnotations(self, returnPaths: bool = False) -> list[dict]:
        model: AnnotationTreeModel = self.model()
        if model is None:
            if returnPaths:
                return [], []
            return []
        annotations = []
        if returnPaths:
            paths = []
        for index in self.selectionModel().selectedIndexes():
            item = model.itemFromIndex(index)
            if item is None:
                continue
            if item.isLeaf():
                annotation = getattr(item, '_data', None)
                if annotation is not None:
                    annotations.append(annotation)
                    if returnPaths:
                        parentItem = item.parent()
                        if isinstance(parentItem._data, str):
                            parentItem = item.parent()
                        obj = parentItem._data
                        if isinstance(obj, xr.DataTree):
                            paths.append(obj.path)
                        elif isinstance(obj, xr.DataArray):
                            name = obj.name
                            obj = parentItem.parent()._data
                            paths.append(f'{obj.path}/{name}')
                        else:
                            paths.append(None)
        if returnPaths:
            return annotations, paths
        return annotations

    def setSelectedAnnotations(self, annotations: list[dict]) -> None:
        self.selectionModel().clearSelection()
        toSelect = QItemSelection()
        for item in self.model().root().depthFirst():
            if item is self.model().root():
                continue
            if item.isLeaf():
                annotation = getattr(item, '_data', None)
                if annotation is not None:
                    if annotation in annotations:
                        index = self.model().indexFromItem(item)
                        toSelect.select(index, index)
        if toSelect.indexes():
            flags = (
                QItemSelectionModel.SelectionFlag.Select |
                QItemSelectionModel.SelectionFlag.Rows
            )
            self.selectionModel().select(toSelect, flags)
        self._clearSelectionAccumulators()
        self._updateSelection()
    
    @Slot(QItemSelection, QItemSelection)
    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection):
        if not getattr(self, '_is_updating_selection', False):
            # accumulate selected and deselected items
            selectedItems = getattr(self, '_selected_items', [])
            deselectedItems = getattr(self, '_deselected_items', [])
            for index in selected.indexes():
                item = self.model().itemFromIndex(index)
                if item not in selectedItems:
                    selectedItems.append(item)
                if item in deselectedItems:
                    deselectedItems.remove(item)
            for index in deselected.indexes():
                item = self.model().itemFromIndex(index)
                if item not in deselectedItems:
                    deselectedItems.append(item)
                if item in selectedItems:
                    selectedItems.remove(item)
            self._selected_items = selectedItems
            self._deselected_items = deselectedItems

            # print('-' * 80)
            # print('selectedItems [')
            # for item in selectedItems:
            #     print(item.name)
            # print(']')
            # print('deselectedItems [')
            # for item in deselectedItems:
            #     print(item.name)
            # print(']')

        TreeView.selectionChanged(self, selected, deselected)
    
    def _clearSelectionAccumulators(self) -> None:
        self._selected_items = []
        self._deselected_items = []
    
    def _updateSelection(self, event: QMouseEvent = None) -> None:
        self._is_updating_selection = True

        mouseItem = None
        if event is not None:
            pos = event.pos()
            mouseIndex = self.indexAt(pos)
            mouseItem = self.model().itemFromIndex(mouseIndex)
            mouseItemSelected = self.selectionModel().isSelected(mouseIndex)

        # grab accumulated selections
        selectedItems = getattr(self, '_selected_items', [])
        deselectedItems = getattr(self, '_deselected_items', [])

        # Deselect all ancestors and descendents of each deselected item.
        # The deselected items are accumulated in the selectionChanged() method.
        if deselectedItems:
            toDeselect = QItemSelection()
            for item in deselectedItems:
                ancestor = item.parent()
                while ancestor is not None:
                    if mouseItem is not None and mouseItemSelected:
                        if ancestor.hasAncestor(mouseItem):
                            break
                    ancestorIndex = self.model().indexFromItem(ancestor)
                    if self.selectionModel().isSelected(ancestorIndex):
                        toDeselect.select(ancestorIndex, ancestorIndex)
                    ancestor = ancestor.parent()
                for descendant in item.depthFirst():
                    if descendant is item:
                        continue
                    if not descendant.hasAncestor(item):
                        break
                    if mouseItem is not None and mouseItemSelected:
                        if descendant.hasAncestor(mouseItem):
                            continue
                    descendantIndex = self.model().indexFromItem(descendant)
                    if self.selectionModel().isSelected(descendantIndex):
                        toDeselect.select(descendantIndex, descendantIndex)
            if toDeselect.indexes():
                flags = (
                    QItemSelectionModel.SelectionFlag.Deselect |
                    QItemSelectionModel.SelectionFlag.Rows
                )
                self.selectionModel().select(toDeselect, flags)
        
        # Ensure selected items are selected.
        # The selected items are accumulated in the selectionChanged() method.
        if selectedItems:
            toSelect = QItemSelection()
            for item in selectedItems:
                index = self.model().indexFromItem(item)
                if not self.selectionModel().isSelected(index):
                    toSelect.select(index, index)
            if toSelect.indexes():
                flags = (
                    QItemSelectionModel.SelectionFlag.Select |
                    QItemSelectionModel.SelectionFlag.Rows
                )
                self.selectionModel().select(toSelect, flags)
        
        # Select all descendents of each selected item.
        # Also select all items for which all child items are selected.
        toSelect = QItemSelection()
        indexes = self.selectionModel().selectedIndexes()
        for index in indexes:
            item = self.model().itemFromIndex(index)
            for descendant in item.depthFirst():
                descendantIndex = self.model().indexFromItem(descendant)
                if not self.selectionModel().isSelected(descendantIndex):
                    toSelect.select(descendantIndex, descendantIndex)
        for item in self.model().root().reverseDepthFirst():
            if item is self.model().root():
                continue
            if item.isLeaf():
                continue
            allChildrenSelected = True
            for child in item.children:
                childIndex = self.model().indexFromItem(child)
                if not self.selectionModel().isSelected(childIndex):
                    allChildrenSelected = False
                    break
            if allChildrenSelected:
                itemIndex = self.model().indexFromItem(item)
                if not self.selectionModel().isSelected(itemIndex):
                    toSelect.select(itemIndex, itemIndex)
        if toSelect.indexes():
            flags = (
                QItemSelectionModel.SelectionFlag.Select |
                QItemSelectionModel.SelectionFlag.Rows
            )
            self.selectionModel().select(toSelect, flags)
        
        self._clearSelectionAccumulators()
        self._is_updating_selection = False
    
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._updateSelection(event)
        TreeView.mouseReleaseEvent(self, event)
    
    def contextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu:
        menu: QMenu = TreeView.contextMenu(self, index)

        menu.addSeparator()

        return menu
    
    # def popupItemInfo(self, item: AbstractTreeItem):
    #     model: XarrayTreeModel = self.model()
    #     if model is None:
    #         return
    #     dt: xr.DataTree | None = model.dataTree()
    #     if dt is None:
    #         return
    #     path: str = model.pathFromItem(item)
    #     obj = dt[path]
    #     text = str(obj)
        
    #     textEdit = QTextEdit()
    #     textEdit.setPlainText(text)
    #     textEdit.setReadOnly(True)

    #     dlg = QDialog(self)
    #     dlg.setWindowTitle(item.path)
    #     layout = QVBoxLayout(dlg)
    #     layout.setContentsMargins(0, 0, 0, 0)
    #     layout.addWidget(textEdit)
    #     dlg.exec()
    
    # def editItemAttrs(self, item: AbstractTreeItem):
    #     model: XarrayTreeModel = self.model()
    #     if model is None:
    #         return
    #     dt: xr.DataTree | None = model.dataTree()
    #     if dt is None:
    #         return
    #     path: str = model.pathFromItem(item)
    #     obj = dt[path]
    #     attrs = obj.attrs.copy()
        
    #     root = KeyValueTreeItem('/', attrs)
    #     kvmodel = KeyValueTreeModel(root)
    #     view = KeyValueTreeView()
    #     view.setModel(kvmodel)
    #     view.expandAll()
    #     view.resizeAllColumnsToContents()

    #     dlg = QDialog(self)
    #     dlg.setWindowTitle(item.path)
    #     layout = QVBoxLayout(dlg)
    #     layout.setContentsMargins(0, 0, 0, 0)
    #     layout.addWidget(view)

    #     btns = QDialogButtonBox()
    #     btns.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
    #     btns.accepted.connect(dlg.accept)
    #     btns.rejected.connect(dlg.reject)
    #     layout.addWidget(btns)
        
    #     dlg.setWindowModality(Qt.ApplicationModal)
    #     dlg.setMinimumSize(QSize(400, 400))
    #     if dlg.exec() != QDialog.Accepted:
    #         return
        
    #     attrs = kvmodel.root().value
    #     obj.attrs = attrs
        
    #     self.sigFinishedEditingAttrs.emit()


def test_live():
    print('\nDataTree...')
    dt = xr.DataTree()
    dt['child1'] = xr.tutorial.load_dataset('air_temperature')
    dt['child2'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild1'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild2'] = xr.DataTree()
    dt['child3/grandchild2'] = xr.DataTree()
    
    dt.attrs['annotations'] = [
        {'type': 'vregion', 'position': {'lat': [0, 1]}},
        {'type': 'vregion', 'position': {'lat': [2, 3]}, 'group': 'group2', 'text': '10 mM GABA\n1 mM PTX'},
    ]
    dt['child1'].attrs['annotations'] = [
        {'type': 'vregion', 'position': {'lat': [0, 1]}, 'group': 'group1'},
        {'type': 'vregion', 'position': {'lat': [2, 3]}, 'group': 'group1'},
        {'type': 'vregion', 'position': {'lat': [2, 3]}, 'group': 'group2'},
    ]
    # print(dt)
    import json
    print(json.dumps(dt['child1'].attrs['annotations'], indent=2))

    print('\nAnnotationTreeModel...')
    model = AnnotationTreeModel(dt=dt, key='annotations')#, paths=['child1', 'child2'])
    # print(model.root())

    app = QApplication()
    view = AnnotationTreeView()
    view.setModel(model)
    view.show()
    view.resize(400, 350)
    app.exec()
    print('\nFinal DataTree...')
    # print(dt)
    print(json.dumps(dt['child1'].attrs['annotations'], indent=2))


if __name__ == '__main__':
    test_live()
