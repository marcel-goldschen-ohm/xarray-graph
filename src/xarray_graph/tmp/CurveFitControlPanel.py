""" Curve fit control panel UI.
"""

from __future__ import annotations
import numpy as np
import scipy as sp
import lmfit
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *


class CurveFitControlPanel(QWidget):

    fitChanged = Signal()
    previewToggled = Signal()
    applyFitRequested = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setWindowTitle('Curve Fit')

        # components
        self._label = QLabel('Curve Fit')

        self._type_combobox = QComboBox()
        self._type_combobox.addItems(['Mean', 'Median', 'Min', 'Max'])
        self._type_combobox.insertSeparator(self._type_combobox.count())
        self._type_combobox.addItems(['Line', 'Polynomial', 'Spline'])
        self._type_combobox.insertSeparator(self._type_combobox.count())
        self._type_combobox.addItems(['Expression'])
        self._type_combobox.setCurrentText('Expression')
        self._type_combobox.currentIndexChanged.connect(lambda index: self._onFitTypeChanged())

        self._named_expressions = {
            'Gaussian': {
                'expression': 'a * exp(-(x-b)**2 / (2 * c**2))',
                'params': {
                    'a': {'value': 1, 'vary': True, 'min': 0, 'max': np.inf},
                    'b': {'value': 0, 'vary': True, 'min': -np.inf, 'max': np.inf},
                    'c': {'value': 1, 'vary': True, 'min': 0, 'max': np.inf},
                },
            },
            'Hill Equation': {
                'expression': 'Y0 + Y1 / (1 + (EC50 / x)**n)',
                'params': {
                    'Y0': {'value': 0, 'vary': False, 'min': -np.inf, 'max': np.inf},
                    'Y1': {'value': 1, 'vary': True, 'min': -np.inf, 'max': np.inf},
                    'EC50': {'value': 1, 'vary': True, 'min': 1e-15, 'max': np.inf},
                    'n': {'value': 1, 'vary': True, 'min': 1e-2, 'max': 10},
                },
            },
        }
        if self._named_expressions:
            self._type_combobox.insertSeparator(self._type_combobox.count())
            self._type_combobox.addItems(list(self._named_expressions.keys()))

        # polynomial
        self._polynomial_degree_spinbox = QSpinBox()
        self._polynomial_degree_spinbox.setMinimum(0)
        self._polynomial_degree_spinbox.setMaximum(100)
        self._polynomial_degree_spinbox.setValue(2)
        self._polynomial_degree_spinbox.valueChanged.connect(lambda value: self.fitChanged.emit())

        self._polynomial_groupbox = QGroupBox()
        form = QFormLayout(self._polynomial_groupbox)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Degree', self._polynomial_degree_spinbox)

        # spline
        self._spline_segments_spinbox = QSpinBox()
        self._spline_segments_spinbox.setValue(10)
        self._spline_segments_spinbox.setMinimum(1)
        self._spline_segments_spinbox.valueChanged.connect(lambda value: self.fitChanged.emit())

        self._spline_groupbox = QGroupBox()
        form = QFormLayout(self._spline_groupbox)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('# Segments', self._spline_segments_spinbox)

        # y = f(x)
        self._expression_edit = QLineEdit()
        self._expression_edit.setPlaceholderText('a * x + b')
        self._expression_edit.editingFinished.connect(self._onExpressionChanged)

        self._expression_params_table = QTableWidget(0, 5)
        self._expression_params_table.setHorizontalHeaderLabels(['Param', 'Start', 'Vary', 'Min', 'Max'])
        self._expression_params_table.verticalHeader().setVisible(False)
        self._expression_params_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._expression_params_table.model().dataChanged.connect(lambda model_index: self.fitChanged.emit())

        self._expression_groupbox = QGroupBox()
        vbox = QVBoxLayout(self._expression_groupbox)
        vbox.setContentsMargins(3, 3, 3, 3)
        vbox.setSpacing(3)
        vbox.addWidget(self._expression_edit)
        vbox.addWidget(self._expression_params_table)

        # options and buttons
        self._limit_input_to_ROIs_checkbox = QCheckBox('Optimize within ROIs only', checked=True)
        self._limit_input_to_ROIs_checkbox.stateChanged.connect(lambda state: self.fitChanged.emit())

        self._limit_output_to_ROIs_checkbox = QCheckBox('Fit within ROIs only', checked=False)
        self._limit_output_to_ROIs_checkbox.stateChanged.connect(lambda state: self.fitChanged.emit())

        self._residuals_checkbox = QCheckBox('Residuals', checked=False)
        self._residuals_checkbox.stateChanged.connect(lambda state: self.fitChanged.emit())

        self._preview_checkbox = QCheckBox('Preview', checked=True)
        self._preview_checkbox.stateChanged.connect(lambda state: self.previewToggled.emit())

        self._apply_button = QPushButton('Fit')
        self._apply_button.pressed.connect(lambda: self.applyFitRequested.emit())

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(self._preview_checkbox)
        buttons_layout.addWidget(self._apply_button)

        self._spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)

        # layout
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.setSpacing(5)
        # vbox.addWidget(self._label)
        vbox.addWidget(self._type_combobox)
        vbox.addWidget(self._polynomial_groupbox)
        vbox.addWidget(self._spline_groupbox)
        vbox.addWidget(self._expression_groupbox)
        vbox.addSpacing(10)
        vbox.addWidget(self._limit_input_to_ROIs_checkbox)
        vbox.addWidget(self._limit_output_to_ROIs_checkbox)
        vbox.addWidget(self._residuals_checkbox)
        vbox.addSpacing(10)
        vbox.addLayout(buttons_layout)
        vbox.addSpacerItem(self._spacer)

        self.blockSignals(True)
        self._onFitTypeChanged()
        self.blockSignals(False)
    
    def _onFitTypeChanged(self) -> None:
        fit_types = [self._type_combobox.itemText(i) for i in range(self._type_combobox.count())]
        fit_type = self._type_combobox.currentText()
        is_polynomial = fit_type == 'Polynomial'
        is_spline = fit_type == 'Spline'
        is_expression = self._type_combobox.currentIndex() >= fit_types.index('Expression')
        self._polynomial_groupbox.setVisible(is_polynomial)
        self._spline_groupbox.setVisible(is_spline)
        self._expression_groupbox.setVisible(is_expression)
        if is_expression:
            self._spacer.changeSize(0, 0, QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        else:
            self._spacer.changeSize(0, 0, QSizePolicy.Policy.Ignored, QSizePolicy.Policy.MinimumExpanding)
        
        # to avoid focus remaining on a hidden element (shows part of focus highlight when it shouldn't)
        if is_polynomial:
            self._polynomial_degree_spinbox.setFocus()
        elif is_spline:
            self._spline_segments_spinbox.setFocus()
        elif is_expression:
            self._expression_edit.setFocus()
        else:
            self._apply_button.setFocus()
        
        self.fitChanged.emit()
    
    def _onExpressionChanged(self) -> None:
        expression = self._expression_edit.text().strip()     
        if expression == '':
            self.setExpressionTableParams({})
        else:
            model = lmfit.models.ExpressionModel(expression, independent_vars=['x'])
            old_params: dict = self.expressionTableParams()
            new_params = {}
            for name in model.param_names:
                if name in old_params:
                    new_params[name] = old_params[name]
                else:
                    new_params[name] = {
                        'value': 0,
                        'vary': True,
                        'min': -np.inf,
                        'max': np.inf
                    }
            self.setExpressionTableParams(new_params)
        
        self.fitChanged.emit()
    
    def expressionModel(self) -> lmfit.models.ExpressionModel | None:
        expression = self._expression_edit.text().strip()
        if 'x' not in expression:
            return None
        model = lmfit.models.ExpressionModel(expression, independent_vars=['x'])
        params = self.expressionTableParams()
        for name in model.param_names:
            model.set_param_hint(name, **params[name])
        return model
    
    def expressionTableParams(self) -> dict:
        params = {}
        for row in range(self._expression_params_table.rowCount()):
            name = self._expression_params_table.item(row, 0).text()
            try:
                value = float(self._expression_params_table.item(row, 1).text())
            except:
                value = 0
            vary = self._expression_params_table.item(row, 2).checkState() == Qt.CheckState.Checked
            try:
                value_min = float(self._expression_params_table.item(row, 3).text())
            except:
                value_min = -np.inf
            try:
                value_max = float(self._expression_params_table.item(row, 4).text())
            except:
                value_max = np.inf
            params[name] = {
                'value': value,
                'vary': vary,
                'min': value_min,
                'max': value_max
            }
        return params
    
    def setExpressionTableParams(self, params: dict | lmfit.Parameters) -> None:
        if isinstance(params, lmfit.Parameters):
            params = params.valuesdict()

        self._expression_params_table.model().dataChanged.disconnect()  # needed because blockSignals not working!?
        self._expression_params_table.blockSignals(True)  # not working!?
        self._expression_params_table.clearContents()
        
        self._expression_params_table.setRowCount(len(params))
        row = 0
        name: str
        attrs: dict
        for name, attrs in params.items():
            value = attrs.get('value', 0)
            vary = attrs.get('vary', True)
            value_min = attrs.get('min', -np.inf)
            value_max = attrs.get('max', np.inf)

            name_item = QTableWidgetItem(name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            value_item = QTableWidgetItem(f'{value:.6g}')
            vary_item = QTableWidgetItem()
            vary_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            vary_item.setCheckState(Qt.CheckState.Checked if vary else Qt.CheckState.Unchecked)
            min_item = QTableWidgetItem(str(value_min))
            max_item = QTableWidgetItem(str(value_max))

            for col, item in enumerate([name_item, value_item, vary_item, min_item, max_item]):
                self._expression_params_table.setItem(row, col, item)
            row += 1
        
        self._expression_params_table.resizeColumnsToContents()
        self._expression_params_table.blockSignals(False)
        self._expression_params_table.model().dataChanged.connect(lambda model_index: self.fitChanged.emit())  # needed because blockSignals not working!?
    
    def fit(self, x: np.ndarray, y: np.ndarray) -> dict:
        """ Fit y(x)
        """

        fit_type = self._type_combobox.currentText()
        fit_result = {
            'type': fit_type
        }

        if fit_type not in ['Mean', 'Median', 'Min', 'Max']:
            # remove any (x,y) pairs that contain NaN
            mask = np.isnan(x) | np.isnan(y)
            if np.any(mask):
                x = x[~mask]
                y = y[~mask]
        
        if fit_type == 'Mean':
            fit_result['value'] = np.nanmean(y)
        elif fit_type == 'Median':
            fit_result['value'] = np.nanmedian(y)
        elif fit_type == 'Min':
            fit_result['value'] = np.nanmin(y)
        elif fit_type == 'Max':
            fit_result['value'] = np.nanmax(y)
        elif fit_type == 'Line':
            fit_result['coef'] = np.polyfit(x, y, 1)
        elif fit_type == 'Polynomial':
            degree = self._polynomial_degree_spinbox.value()
            fit_result['degree'] = degree
            fit_result['coef'] = np.polyfit(x, y, degree)
        # elif fit_type == 'BSpline':
        #     # !? this is SLOW for even slightly large arrays
        #     n_pts = len(x)
        #     degree = self._bspline_degree_spinbox.value()
        #     smoothing = self._bspline_smoothing_spinbox.value()
        #     if smoothing == 0:
        #         smoothing = n_pts
        #     n_knots = self._bspline_knots_spinbox.value()
        #     if n_knots == 0:
        #         n_knots = None
        #     else:
        #         # ensure valid number of knots
        #         n_knots = min(max(2 * degree + 2, n_knots), n_pts + degree + 1)
        #     bspline: sp.interpolate.BSpline = sp.interpolate.make_splrep(x, y, s=smoothing, nest=n_knots)
        #     fit_result['bspline'] = bspline
        elif fit_type == 'Spline':
            n_segments = self._spline_segments_spinbox.value()
            segment_length = max(3, int(len(x) / n_segments))
            knots = x[segment_length:-segment_length:segment_length]
            knots, coef, degree = sp.interpolate.splrep(x, y, t=knots)
            fit_result['knots'] = knots
            fit_result['coef'] = coef
            fit_result['degree'] = degree
        elif fit_type == 'Expression' or fit_type in list(self._named_expressions.keys()):
            model: lmfit.models.ExpressionModel = self.expressionModel()
            if model is None:
                return None
            result: lmfit.model.ModelResult = model.fit(y, params=model.make_params(), x=x)
            # print(result.fit_report())
            fit_result['result'] = result
        
        return fit_result
    
    def predict(self, x: np.ndarray, fit_result: dict) -> np.ndarray:
        """ Eval fit(x)
        """

        fit_type = self._type_combobox.currentText()
        if fit_type in ['Mean', 'Median', 'Min', 'Max']:
            value = fit_result['value']
            ypred = np.full(len(x), value)
        elif fit_type in ['Line', 'Polynomial']:
            coef = fit_result['coef']
            ypred = np.polyval(coef, x)
        # elif fit_type == 'BSpline':
        #     bspline: sp.interpolate.BSpline = fit_result['bspline']
        #     ydata = bspline(x)
        elif fit_type == 'Spline':
            knots, coef, degree = [fit_result[key] for key in ['knots', 'coef', 'degree']]
            ypred = sp.interpolate.splev(x, (knots, coef, degree ), der=0)
        elif fit_type == 'Expression' or fit_type in list(self._named_expressions.keys()):
            if fit_result is None:
                model = self.expressionModel()
                if model is None:
                    return None
                params = model.make_params()
            else:
                result: lmfit.model.ModelResult = fit_result['result']
                model: lmfit.models.ExpressionModel = result.model
                params = result.params
            ypred = model.eval(params=params, x=x)
        
        return ypred


def test_live():
    app = QApplication()
    ui = CurveFitControlPanel()
    ui.show()
    app.exec()


if __name__ == '__main__':
    test_live()