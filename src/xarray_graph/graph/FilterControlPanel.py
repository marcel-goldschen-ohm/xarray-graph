""" Filter control panel UI.
"""

from __future__ import annotations

from qtpy.QtCore import Signal
from qtpy.QtWidgets import QWidget

import typing
if typing.TYPE_CHECKING:
    import numpy as np
    from xarray import DataArray
    from pint import UnitRegistry


class FilterControlPanel(QWidget):

    filterChanged = Signal()
    previewToggled = Signal()
    filterRequested = Signal()
    panelClosed = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        from qtpy.QtWidgets import QLabel, QComboBox, QLineEdit, QGroupBox, QFormLayout, QCheckBox, QPushButton, QHBoxLayout, QVBoxLayout

        self.setWindowTitle('Filter')

        # components
        self._label = QLabel('Filter')

        self._type_combobox = QComboBox()
        self._type_combobox.addItems(['Gaussian', 'Median', 'Bessel', 'Butterworth', 'FIR'])
        self._type_combobox.setCurrentText('Gaussian')
        self._type_combobox.currentIndexChanged.connect(lambda index: self._onFilterChanged())
        self._type_combobox.setEnabled(False) # only Gaussian filter working at the moment

        self._band_type_combobox = QComboBox()
        self._band_type_combobox.addItems(['Lowpass', 'Highpass', 'Bandpass', 'Bandstop'])
        self._band_type_combobox.setCurrentText('Lowpass')
        self._band_type_combobox.currentIndexChanged.connect(lambda index: self._onFilterChanged())

        self._cutoff_edit = QLineEdit('')
        self._cutoff_edit.setPlaceholderText('1 Hz [, 1 kHz]')
        self._cutoff_edit.setToolTip('single [, band]')
        self._cutoff_edit.editingFinished.connect(lambda: self.filterChanged.emit())

        self._band_group = QGroupBox()
        form = QFormLayout(self._band_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow(self._band_type_combobox)
        form.addRow('Cutoff', self._cutoff_edit)

        self._preview_checkbox = QCheckBox('Preview', checked=True)
        self._preview_checkbox.stateChanged.connect(lambda state: self.previewToggled.emit())

        self._apply_button = QPushButton('Apply')
        self._apply_button.pressed.connect(lambda: self.filterRequested.emit())

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(self._preview_checkbox)
        buttons_layout.addWidget(self._apply_button)

        # layout
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.setSpacing(5)
        # vbox.addWidget(self._label)
        vbox.addWidget(self._type_combobox)
        vbox.addWidget(self._band_group)
        vbox.addLayout(buttons_layout)
        vbox.addStretch()

        self.blockSignals(True)
        self._onFilterChanged()
        self.blockSignals(False)
    
    def state(self) -> dict:
        return {
            'filter': self._type_combobox.currentText(),
            'band': self._band_type_combobox.currentText(),
            'cutoff': self._cutoff_edit.text(),
            'preview': self._preview_checkbox.isChecked()
        }

    def setState(self, state: dict) -> None:
        self.blockSignals(True)
        self._type_combobox.setCurrentText(state.get('filter', 'Gaussian'))
        self._band_type_combobox.setCurrentText(state.get('band', 'Lowpass'))
        self._cutoff_edit.setText(state.get('cutoff', ''))
        self._preview_checkbox.setChecked(state.get('preview', True))
        self.blockSignals(False)
        self._onFilterChanged()

    def _onFilterChanged(self) -> None:
        filter_type = self._type_combobox.currentText()

        from qtpy.QtCore import QSignalBlocker

        if filter_type == 'Gaussian':
            with QSignalBlocker(self._band_type_combobox):
                self._band_type_combobox.setCurrentText('Lowpass')
                self._band_type_combobox.setEnabled(False)
        
        band_type = self._band_type_combobox.currentText()
        if band_type in ['Lowpass', 'Highpass']:
            self._cutoff_edit.setPlaceholderText('1 kHz')
            self._cutoff_edit.setToolTip('cutoff frequency and units (no units -> cycles/sample)')
        elif band_type in ['Bandpass', 'Bandstop']:
            self._cutoff_edit.setPlaceholderText('1 kHz, 10 kHz')
            self._cutoff_edit.setToolTip('cutoff frequencies and units (no units -> cycles/sample)')

        self.filterChanged.emit()
    
    def filter(self, x: DataArray | np.ndarray, y: DataArray | np.ndarray, ureg: UnitRegistry = None, xunits: str = None) -> DataArray | np.ndarray:
        import numpy as np
        from xarray import DataArray

        filter_type = self._type_combobox.currentText()
        band_type = self._band_type_combobox.currentText()
        cutoffs = [ureg.Quantity(fc) for fc in self._cutoff_edit.text().split(',') if fc.strip() != '']
        if not cutoffs:
            return
        
        if isinstance(x, DataArray):
            xdata = x.data
            if xunits is None:
                xunits = x.attrs.get('units', None)
        elif isinstance(x, np.ndarray):
            xdata = x
        dx = (xdata[1] - xdata[0])  # !!! assumes constant sample rate
        if xunits:
            dx *= ureg(xunits)
        
        if isinstance(y, DataArray):
            ydata = y.data
        elif isinstance(y, np.ndarray):
            ydata = y
        
        use_cutoff_units = [(not cutoff.dimensionless and cutoff.units and xunits) for cutoff in cutoffs]

        if filter_type == 'Gaussian':
            # must be lowpass
            lowpass_cutoff = cutoffs[0]
            if use_cutoff_units[0]:
                lowpass_cycles_per_sample = (lowpass_cutoff.to(f'1/{xunits}') * dx).magnitude
            else:
                lowpass_cycles_per_sample = lowpass_cutoff.magnitude
            sigma = 1 / (2 * np.pi * lowpass_cycles_per_sample)
            from scipy.ndimage import gaussian_filter1d
            yfiltered = gaussian_filter1d(ydata, sigma)
        
        if isinstance(y, DataArray):
            return y.copy(data=yfiltered)
        elif isinstance(y, np.ndarray):
            return yfiltered

    def filterType(self) -> str:
        return self._type_combobox.currentText()

    def setFilterType(self, filter_type: str):
        self._type_combobox.setCurrentText(filter_type)

    def cutoffString(self) -> str:
        cutoffs = self._cutoff_edit.text().split(',')
        if len(cutoffs) == 1:
            return cutoffs[0].strip()
        elif len(cutoffs) == 2:
            return f'{cutoffs[0].strip()}-{cutoffs[1].strip()}'

    def isPreview(self) -> bool:
        return self._preview_checkbox.isChecked()
    
    def closeEvent(self, event):
        status = super().closeEvent(event)
        from qtpy.QtCore import QTimer
        QTimer.singleShot(0, self.panelClosed.emit)
        return status


def test_live():
    from qtpy.QtWidgets import QApplication
    app = QApplication()
    ui = FilterControlPanel()
    ui.show()
    app.exec()


if __name__ == '__main__':
    test_live()