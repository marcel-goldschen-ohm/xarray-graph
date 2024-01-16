from xarray_graph.XarrayGraph import XarrayGraph
from qtpy.QtWidgets import QApplication


def main():
    app = QApplication()
    ui = XarrayGraph()
    ui.setWindowTitle(ui.__class__.__name__)
    ui.show()
    app.exec()


if __name__ == '__main__':
    main()
