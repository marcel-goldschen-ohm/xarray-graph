""" Tree view of a AnnotationTreeModel with context menu and mouse wheel expand/collapse.
"""

from __future__ import annotations
from typing import Callable
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
from pyqt_ext.tree import TreeView, KeyValueTreeModel, KeyValueTreeView
from xarray_graph import AnnotationTreeItem, AnnotationTreeModel


class AnnotationTreeView(TreeView):

    def __init__(self, parent: QObject = None) -> None:
        TreeView.__init__(self, parent)

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    
    def setDataTree(self, datatree: xr.DataTree, paths: list[str] = None, attrs_key: str = 'annotations'):
        model: AnnotationTreeModel = self.model()
        if model is None:
            model = AnnotationTreeModel()
            TreeView.setModel(self, model)
        self.storeState()
        model.setDataTree(datatree, paths=paths, attrs_key=attrs_key)
        self.restoreState()
        self._paths = paths
        self._attrs_key = attrs_key
    
    def refresh(self):
        model: AnnotationTreeModel = self.model()
        if model is None:
            return
        datatree: xr.DataTree | None = model.dataTree()
        if datatree is None:
            return
        paths = getattr(self, '_paths', None)
        attrs_key = getattr(self, '_attrs_key', 'annotations')
        self.setDataTree(datatree, paths=paths, attrs_key=attrs_key)
    
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
                annotation = getattr(item, 'data', None)
                if annotation is not None:
                    annotations.append(annotation)
                    if returnPaths:
                        parentItem = item.parent()
                        if isinstance(parentItem.data, str):
                            parentItem = item.parent()
                        obj = parentItem.data
                        if isinstance(obj, xr.DataTree):
                            paths.append(obj.path)
                        elif isinstance(obj, xr.DataArray):
                            name = obj.name
                            obj = parentItem.parent().data
                            paths.append(f'{obj.path}/{name}')
                        else:
                            paths.append(None)
        if returnPaths:
            return annotations, paths
        return annotations

    def setSelectedAnnotations(self, annotations: list[dict]) -> None:
        self.selectionModel().clearSelection()
        toSelect = QItemSelection()
        for item in self.model().rootItem().depthFirst():
            if item is self.model().rootItem():
                continue
            if item.isLeaf():
                annotation = getattr(item, 'data', None)
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
            # print('selectedItems', [item.name() for item in selectedItems])
            # print('deselectedItems', [item.name() for item in deselectedItems])

        TreeView.selectionChanged(self, selected, deselected)

        mouseButtons = QApplication.mouseButtons()
        if mouseButtons == Qt.MouseButton.NoButton:
            # this is needed because deselection of a part of an extended selection
            # does not trigger a selectionChanged event until after the mouse button is released
            self._updateSelection()
    
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

        # print('-' * 80)
        # print('final selectedItems', [item.name() for item in selectedItems])
        # print('final deselectedItems', [item.name() for item in deselectedItems])

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
        for item in self.model().rootItem().reverseDepthFirst():
            if item is self.model().rootItem():
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
    
    def customContextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu | None:
        model: AnnotationTreeModel = self.model()
        if model is None:
            return
        
        menu = QMenu(self)

        # context menu for item that was clicked on
        if index.isValid():
            item: AnnotationTreeItem = model.itemFromIndex(index)
            item_label = self.truncateLabel(item.path())
            if item.isAnnotationDict():
                menu.addAction(f'Edit {item_label}', lambda item=item: self.editAnnotation(item))
                menu.addSeparator()
            menu.addAction(f'Remove {item_label}', lambda item=item: self.askToRemoveItems([item]))
            menu.addSeparator()
        
        selectedItems = self.selectedItems()
        if selectedItems:
            menu.addAction('Group Selected', self.groupSelectedAnnotations)
            menu.addSeparator()
        
        self.appendDefaultContextMenu(menu)
        return menu
    
    def editAnnotation(self, item: AnnotationTreeItem):
        if not item.isAnnotationDict():
            return
        
        annotation: dict = item.data
        model = KeyValueTreeModel(annotation)
        view = KeyValueTreeView()
        view.setModel(model)
        view.showAll()

        dlg = QDialog(self)
        dlg.setWindowTitle(item.path())
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)

        btns = QDialogButtonBox()
        btns.setStandardButtons(QDialogButtonBox.StandardButton.Close)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setMinimumSize(QSize(400, 400))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            pass # return

        # update item label or tree in case of group change
        self.refresh()

    def groupSelectedAnnotations(self, group: str = None) -> None:
        """ Group selected annotations under a new group name.
        """
        if group is None:
            group, ok = QInputDialog.getText(self, 'Group Annotations', 'Enter group name:')
            if not ok:
                return
        
        group = group.strip()
        if not group:
            return
        
        selectedAnnotations = self.selectedAnnotations(returnPaths=False)
        if not selectedAnnotations:
            return
        
        for annotation in selectedAnnotations:
            annotation['group'] = group
        
        self.refresh()
    
    def dropEvent(self, event: QDropEvent) -> None:
        self.storeState()
        super().dropEvent(event)
        self.restoreState()


def test_live():
    dt = xr.DataTree()
    dt['child1'] = xr.tutorial.load_dataset('air_temperature')
    dt['child2'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild1'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild2'] = xr.DataTree()
    dt['child3/grandchild2'] = xr.DataTree()
    
    dt.attrs['annotations'] = [
        {'type': 'vregion', 'position': {'lat': (0, 1)}},
        {'type': 'vregion', 'position': {'lat': (2, 3)}, 'group': 'group2', 'text': '10 mM GABA\n1 mM PTX'},
    ]
    dt['child1'].attrs['annotations'] = [
        {'type': 'vregion', 'position': {'lat': (0, 1)}, 'group': 'group1'},
        {'type': 'vregion', 'position': {'lat': (2, 3)}, 'group': 'group1'},
        {'type': 'vregion', 'position': {'lat': (2, 3)}, 'group': 'group2'},
    ]

    # print('\nDataTree...')
    # print(dt)

    import json
    print('root annotations:', '-'*42)
    print(json.dumps(dt.attrs['annotations'], indent=2))
    print('child1 annotations:', '-'*42)
    print(json.dumps(dt['child1'].attrs['annotations'], indent=2))

    model = AnnotationTreeModel(datatree=dt, attrs_key='annotations')#, paths=['child1', 'child2'])
    
    # print('\nAnnotationTreeModel...')
    # print(model.root())

    app = QApplication()
    view = AnnotationTreeView()
    view.setModel(model)
    view.show()
    view.resize(400, 350)
    app.exec()
    
    # print('\nFinal DataTree...')
    # print(dt)

    print('root annotations:', '-'*42)
    print(json.dumps(dt.attrs['annotations'], indent=2))
    print('child1 annotations:', '-'*42)
    print(json.dumps(dt['child1'].attrs['annotations'], indent=2))


if __name__ == '__main__':
    test_live()
