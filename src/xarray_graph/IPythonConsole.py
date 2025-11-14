""" PyQt embedded IPython console for interacting with an Xarray DataTree.
"""

from __future__ import annotations
from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtconsole.inprocess import QtInProcessKernelManager


class IPythonConsole(RichJupyterWidget):
    """ PyQt embedded IPython console for interacting with an Xarray DataTree.
    
    To update another UI element when code is executed in the console,
    connect to the `executed` signal:
        self.executed.connect(your_update_function)
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.kernel_manager = QtInProcessKernelManager()
        self.kernel_manager.start_kernel(show_banner=False)
        self.kernel_client = self.kernel_manager.client()
        self.kernel_client.start_channels()

        self.execute('import numpy as np', hidden=True)
        self.execute('import xarray as xr', hidden=True)
        # self._set_input_buffer('') # seems silly to have to call this?
    
    # def __del__(self) -> None:
    #     """ Shutdown the embedded console.
    #     """
    #     self.kernel_client.stop_channels()
    #     self.kernel_manager.shutdown_kernel()

    def add_variable(self, name: str, value: object) -> None:
        """ Add a variable to the console's namespace.
        """
        self.kernel_manager.kernel.shell.push({name: value})
    
    def print_message(self, message: str) -> None:
        self._append_plain_text(message, before_prompt=True)
    
    
def test_live():
    from qtpy.QtWidgets import QApplication
    from qtpy.QtCore import QTimer
    import xarray as xr
    import textwrap

    app = QApplication()
    console = IPythonConsole()

    dt = xr.open_datatree('examples/ERPdata.nc', engine='h5netcdf')
    console.add_variable('dt', dt)

    msg = """
    ----------------------------------------------------
    dt -> The Xarray DataTree
    Modules loaded at startup: numpy as np, xarray as xr
    ----------------------------------------------------
    """
    msg = textwrap.dedent(msg).strip()
    # need to delay a bit to let the console show
    QTimer.singleShot(100, lambda: console.print_message(msg))
    
    console.show()
    app.exec()


if __name__ == '__main__':
    test_live()