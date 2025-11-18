""" View of an Xarray DataTree mostly for debugging.
"""

from __future__ import annotations
import numpy as np
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
from xarray_graph import xarray_utils
import cmap


class XarrayDataTreeDebugView(QTextEdit):

    def __init__(self, *args, **kwargs) -> None:
        datatree: xr.DataTree = kwargs.pop('datatree', xr.DataTree())
        super().__init__(*args, **kwargs)

        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        self.setDatatree(datatree)
    
    def datatree(self) -> xr.DataTree:
        return self._datatree
    
    def setDatatree(self, datatree: xr.DataTree) -> None:
        self._datatree = datatree
        self.updateView()
    
    def updateView(self) -> None:
        dt: xr.DataTree = self.datatree()

        ids = []
        for node in xarray_utils.subtree_depth_first_iter(dt):
            for data_var in node.data_vars.values():
                ids.append(id(data_var.data))
            for coord in node.coords.values():
                ids.append(id(coord.data))
        shared_ids = [id_ for id_ in ids if ids.count(id_) > 1]
        cm = cmap.Colormap('viridis')
        colors = cm(np.linspace(0, 1, len(shared_ids)))
        id_colors = {id_: QColor(*[int(255*c) for c in color[:3]]) for id_, color in zip(shared_ids, colors)}
        default_color = self.textColor()
        gray = QColor(150, 150, 150)

        vline = '\u2502'
        hline = '\u2500'
        tee = '\u251C'
        corner = '\u2514'
        bullet = '\u2219'
        grid = '\u229E'
        folder = '\u25A1'
        self.clear()
        for node in xarray_utils.subtree_depth_first_iter(dt):
            prefix = ''
            ancestors = list(node.parents)
            for i, parent in enumerate(ancestors):
                if parent is node.parent:
                    siblings = list(parent.children.values())
                    if node is siblings[-1]:
                        prefix = corner + hline*2 + ' ' + prefix
                    else:
                        prefix = tee + hline*2 + ' ' + prefix
                else:
                    children = list(parent.children.values())
                    ancestor = ancestors[i-1]
                    if ancestor is children[-1]:
                        prefix = ' '*4 + prefix
                    else:
                        prefix = vline + ' '*3 + prefix
            line = f"{prefix}{folder} {node.name or node.path} ({', '.join([f'{dim}: {size}' for dim, size in node.dims.items()])})"
            self.append(line)

            if node.children:
                prefix += vline + ' '*3
            else:
                prefix += ' '*4
            
            for name, data_var in node.data_vars.items():
                id_ = id(data_var.data)
                type_ = type(data_var.data)
                line = f"{prefix}{grid} {name} ({', '.join(list(data_var.dims))})  <{id_}> {type_}".replace(hline, ' ').replace(corner, ' ').replace(tee, vline)
                # if not shared_ids:
                #     line = line.split('<')[0].rstrip()
                i = len(prefix)
                self.append(line[:i])
                if id_ in shared_ids:
                    self.setTextColor(id_colors[id_])
                    self.insertPlainText(line[i:])
                else:
                    self.setTextColor(gray)
                    self.insertPlainText(line[i:])
                self.setTextColor(default_color)
            
            for name, coord in node.coords.items():
                id_ = id(coord.data)
                type_ = type(coord.data)
                line = f"{prefix}{bullet} {name} ({', '.join(list(coord.dims))})  <{id_}> {type_}".replace(hline, ' ').replace(corner, ' ').replace(tee, vline)
                # if not shared_ids:
                #     line = line.split('<')[0].rstrip()
                i = len(prefix)
                self.append(line[:i])
                if id_ in shared_ids:
                    self.setTextColor(id_colors[id_])
                    self.insertPlainText(line[i:])
                else:
                    self.setTextColor(gray)
                    self.insertPlainText(line[i:])
                self.setTextColor(default_color)


def test_live():
    dt = xr.DataTree()
    dt['child1'] = xr.tutorial.load_dataset('air_temperature')
    dt['child1/child2'] = xr.DataTree()
    dt['child3/grandchild1'] = xr.tutorial.load_dataset('air_temperature')
    dt['child3/grandchild1/greatgrandchild1'] = dt['child3/grandchild1'].dataset
    dt['child3/grandchild1/greatgrandchild2'] = xr.tutorial.load_dataset('tiny')
    dt['child3/grandchild2'] = xr.DataTree()
    print(dt)

    app = QApplication()
    viewer = XarrayDataTreeDebugView(datatree=dt)
    viewer.resize(800, 800)
    viewer.show()
    app.exec()


if __name__ == '__main__':
    test_live()