""" Embedded IPython console widget.
"""

from qtpy.QtGui import QKeySequence
from qtpy.QtWidgets import QAction
from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtconsole.inprocess import QtInProcessKernelManager
# from qtconsole.manager import QtKernelManager
import qtawesome as qta


class IPythonConsole(RichJupyterWidget):
    """ Embedded IPython console widget.

    !!! The console is designed as a singleton, so you should only create one instance of this class.
    
    To update another UI element when code is executed in the console,
    connect to the `executed` signal:
        self.executed.connect(your_update_function)
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.start()
        # self.exit_requested.connect(self.stop)
        # QApplication.instance().aboutToQuit.connect(self.stop)

        self._console_action = QAction(
            icon=qta.icon('mdi.console'),
            iconVisibleInMenu=True,
            text='Console',
            toolTip='Show Console',
            checkable=False,
            shortcut=QKeySequence('`'),
            triggered=lambda checked: self.showConsole()
        )
    
    def start(self) -> None:
        manager = QtInProcessKernelManager()
        # manager = QtKernelManager()
        manager.start_kernel()
        client = manager.client()
        client.start_channels()
        self.kernel_manager = manager
        self.kernel_client = client
    
    def stop(self) -> None:
        self.kernel_client.stop_channels()
        self.kernel_manager.shutdown_kernel()
    
    def addVariables(self, variables: dict):
        """ Given a dictionary containing {name: value} pairs, push those variables to the console.
        """
        self.kernel_manager.kernel.shell.push(variables)
    
    def clearConsole(self):
        """ Clears the console.
        """
        self._control.clear()
    
    def showConsole(self) -> None:
        """ Show the console window.

        Override this for custom logic on console showing.
        """
        self.show()
    
    def printMessage(self, message: str, dedent: bool = True) -> None:
        """ Print message to the console.
        """
        if dedent:
            import textwrap
            message = textwrap.dedent(message).strip()
        self._append_plain_text(message, before_prompt=True)
    
    
def test_live():
    from qtpy.QtWidgets import QApplication
    from qtpy.QtCore import QTimer
    import numpy as np

    app = QApplication()
    console = IPythonConsole()

    console.execute('import numpy as np', hidden=True)
    # console._set_input_buffer('') # seems silly to have to call this?

    data = np.random.rand(4, 3)
    console.addVariables({'data': data, 'self': console})

    console.executed.connect(lambda: print("Code executed in console."))

    msg = """
    ----------------------------------------------------
    Variables:
      self -> This console
      data -> Data array
    Modules loaded at startup: numpy as np
    ----------------------------------------------------
    """
    # need to delay a bit to let the console show first
    QTimer.singleShot(100, lambda: console.printMessage(msg))
    
    console.show()
    app.exec()


if __name__ == '__main__':
    test_live()