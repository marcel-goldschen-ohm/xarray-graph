from qtpy.QtWidgets import QApplication, QMessageBox
from xarray_graph.tree import XarrayDataTreeViewer


def main():
    app = QApplication()
    app.setQuitOnLastWindowClosed(False)

    window = XarrayDataTreeViewer.new()
    window.show()
    window.raise_()

    # MacOS Magnet warning
    import platform
    if platform.system() == 'Darwin':
        QMessageBox.warning(window, 'Magnet Warning', 'If you are using the window management software Magnet, please disable it for this app to work properly.')
    
    app.exec()


if __name__ == '__main__':
    main()
