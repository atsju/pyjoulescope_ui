# Copyright 2019 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from PySide2 import QtCore, QtGui, QtWidgets
import sys
import logging


log = logging.getLogger(__name__)

STYLE_SHEET = """
QWidget[cssClass~=title] {
    background: #FFCCDDFF;
    border-top: 1px solid gray;
    border-left: 1px solid gray;
    border-right: 1px solid gray;
    border-color: #FF202020;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
}

QWidget[cssClass~=body] {
    border-bottom: 1px solid gray;
    border-left: 1px solid gray;
    border-right: 1px solid gray;
    border-color: #FF202020;
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
}

"""

SIGNALS = {
    'time': {
        'units': [
            ('samples', 'period'),
            ('microseconds (µs)', 1e-6),
            ('milliseconds (ms)', 1e-3),
            ('seconds (s)', 1),
            ('minutes (m)', 60),
            ('hours (h)', 60 * 60),
            ('days (d)', 60 * 60 * 24),
        ],
        'default_value': 0.5,
    },
    'current': {
        'units': [('nA', 1e-9), ('µA', 1e-6), ('mA', 1e-3), ('A', 1)],
        'default_value': 1.0,
    },
    'voltage': {
        'units': [('mV', 1e-3), ('V', 1)],
        'default_value': 1.0,
    },
    'power': {
        'units': [('nW', 1e-9), ('µW', 1e-6), ('mW', 1e-3), ('W', 1)],
        'default_value': 1.0,
    },
    'energy': {
        'units': {
            'J': [('nJ', 1e-9), ('µJ', 1e-6), ('mJ', 1e-3), ('J', 1)],
            'Wh': [('nWh', 1e-9 * 3600.0), ('µWh', 1e-6 * 3600.0), ('mWh', 1e-3 * 3600.0), ('Wh', 1 * 3600.0)],
        },
        'default_value': 1.0,
        'default_index': 3,
    },
    'charge': {
        'units': {
            'C': [('nC', 1e-9), ('µC', 1e-6), ('mC', 1e-3), ('C', 1)],
            'Ah': [('pAh', 1e-12 * 3600.0), ('nAh', 1e-9 * 3600.0), ('µAh', 1e-6 * 3600.0),
                   ('mAh', 1e-3 * 3600.0), ('Ah', 1 * 3600.0)],
        },
        'default_value': 1.0,
        'default_index': 3,
    },
    'current_range': {
        'default_value': 1,
        'range': [0, 7, 1],  # inclusive
        'float_digits': 0,
    },
    'current_lsb': {
        'default_value': 1,
        'range': [0, 1, 1],  # inclusive
        'float_digits': 0,
    },
    'voltage_lsb': {
        'default_value': 1,
        'range': [0, 1, 1],  # inclusive
        'float_digits': 0,
    },
}

for name, value in SIGNALS.items():
    value['name'] = name

EDGE_SIGNALS = ['current', 'voltage', 'power', 'current_range', 'current_lsb', 'voltage_lsb']
WINDOW_SIGNALS = ['energy', 'charge']


TRIGGER_SETTINGS_DEFAULT = {
    'before_start': {
        'enabled': True,
        'value': 0.001,
        'signal': 'time',
    },
    'start': {
        '__selected__': 'edge',
        'edge': {
            'threshold': {
                'signal': 'current',
                'operation': '>',
                'value': 10e-6,
            },
            'duration_min': {
                'value': 10e-6,
                'signal': 'time',
            },
            'duration_max': {
                'value': 1,
                'signal': 'time',
            },
            'duration_max_enabled': False,
        },
        'window': {
            'threshold': {
                'signal': 'energy',
                'operation': '>',
                'value': 1.0,
            },
            'duration': {
                'value': 0.1,
                'signal': 'time',
            },
        },
    },
    'start_actions': {
        'start_actions': {
            'ram': True,
            'record': False,
        }
    },
    'stop': {
        '__selected__': 'duration',
        'wait': {
            'value': 0.5,
            'signal': 'time',
        },
        'edge': {
            'threshold': {
                'signal': 'current',
                'operation': '<',
                'value': 0.9,
            },
            'duration_min': {
                'value': 10e-6,
                'signal': 'time',
            },
            'duration_max': {
                'value': 1,
                'signal': 'time',
            },
            'duration_max_enabled': False,
        },
    },
    'after_stop': {
        'enabled': False,
        'value': 0.001,
        'signal': 'time',
    },
}


def add_eol_spacer(layout):
    spacer = QtWidgets.QSpacerItem(40, 20,
                                   QtWidgets.QSizePolicy.Expanding,
                                   QtWidgets.QSizePolicy.Minimum)
    layout.addItem(spacer)
    return spacer


class SiValue(QtWidgets.QWidget):

    def __init__(self, parent, name, signal=None, sampling_frequency=None, units=None):
        QtWidgets.QWidget.__init__(self, parent)
        self._sampling_frequency = sampling_frequency
        self._units = units
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._value_spinbox = QtWidgets.QDoubleSpinBox(parent)
        self._value_spinbox.setObjectName(f'{name}_value')
        self._value_spinbox.setRange(0, 10000)
        self._value_spinbox.setSingleStep(1.0)
        self._units_combobox = QtWidgets.QComboBox(parent)
        self._units_combobox.setObjectName(f'{name}_units')
        self._units_combobox.currentIndexChanged.connect(self._on_units_change)
        self._signal = None
        self._units_previous_index = None

        self._layout.addWidget(self._value_spinbox)
        self._layout.addWidget(self._units_combobox)
        self.signal_set(signal)

    @property
    def settings(self):
        return {
            'value': self.value,
            'signal': self._signal['name'],
        }

    @settings.setter
    def settings(self, x):
        self.signal_set(x['signal'])
        self.value = x['value']

    @property
    def _units_enum(self):
        if self._signal is None:
            return None
        if isinstance(self._signal['units'], dict):
            name = self._signal['name']
            units = self._units[name]
            return self._signal['units'][units]
        else:
            return self._signal.get('units')

    def _units_scale(self, index=None):
        if self._units_enum is not None:
            k = self._units_enum[index][-1]
        else:
            k = 1
        if k == 'period':
            k = 1 / self._sampling_frequency
        return k

    def _value_from_index(self, index=None):
        k = self._units_scale(index)
        return k * self._value_spinbox.value()

    @property
    def value(self):
        return self._value_from_index(self._units_combobox.currentIndex())

    @value.setter
    def value(self, k):
        if self._units_enum is None:
            self._value_spinbox.setValue(k)
            return
        block = self._units_combobox.blockSignals(True)
        enum = [(idx, g) for idx, (_, g) in enumerate(self._units_enum)]
        self._value_spinbox.setValue(0.0)
        for idx, g in enum[-1::-1]:
            if k >= g:
                self._units_combobox.setCurrentIndex(idx)
                self._units_previous_index = idx
                self._value_spinbox.setValue(k / g)
                break
        self._units_combobox.blockSignals(block)

    def signal_set(self, signal):
        block = self._units_combobox.blockSignals(True)
        self._units_combobox.clear()
        s = SIGNALS[signal]
        self._signal = s
        units = self._units_enum
        if units is None:
            self._units_combobox.setEnabled(False)
        else:
            self._units_combobox.setEnabled(True)
            for unit_name, _ in units:
                self._units_combobox.addItem(unit_name)
            default_index = s.get('default_index')
            if default_index is None:
                default_index = len(units) - 1
            self._units_combobox.setCurrentIndex(default_index)
            self._units_previous_index = default_index
        self.value = s.get('default_value', 1.0)
        r = s.get('range', [0, 1e9, 1])
        self._value_spinbox.setRange(r[0], r[1])
        self._value_spinbox.setSingleStep(r[2])
        float_digits = s.get('float_digits', 2)
        self._value_spinbox.setDecimals(float_digits)
        self._units_combobox.blockSignals(block)

    def _on_units_change(self, *args, **kwargs):
        k = self._value_from_index(self._units_previous_index)
        k /= self._units_scale(self._units_combobox.currentIndex())
        self._value_spinbox.setValue(k)
        self._units_previous_index = self._units_combobox.currentIndex()


class Section(QtWidgets.QWidget):

    def __init__(self, parent, name):
        QtWidgets.QWidget.__init__(self, parent)
        self._content = []

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.title = QtWidgets.QWidget(self)
        self.title.setObjectName(f'{name}_title')
        self.title.setProperty('cssClass', 'title')
        self.title_layout = QtWidgets.QHBoxLayout(self.title)
        left, top, right, bottom = self.title_layout.getContentsMargins()
        self.title_layout.setContentsMargins(left, int(top / 1.5), right, int(bottom / 1.5))
        self.title_label = QtWidgets.QLabel(name, self.title)
        self.title_layout.addWidget(self.title_label)

        self.content_combobox = QtWidgets.QComboBox(self.title)
        self.content_combobox.setVisible(False)
        self.content_combobox.currentIndexChanged.connect(self._on_content_change)
        self.title_layout.addWidget(self.content_combobox)
        add_eol_spacer(self.title_layout)

        self.body = QtWidgets.QWidget(parent)
        self.body.setObjectName(f'{name}_body')
        self.body.setProperty('cssClass', 'body')
        self.body_layout = QtWidgets.QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(left, int(top / 1.5), right, int(bottom / 1.5))

        self._layout.addWidget(self.title)
        self._layout.addWidget(self.body)

    def _on_content_change(self, index):
        self.body_layout.takeAt(0)
        for name, widget in self._content:
            widget.setVisible(False)
        _, widget = self._content[index]
        self.body_layout.addWidget(widget)
        widget.setVisible(True)

    def add_body_item(self, name, widget, visible=None):
        is_empty = not len(self._content)
        widget.setVisible(False)
        self._content.append((name, widget))
        self.content_combobox.addItem(name)
        if is_empty and visible is False:
            self.content_combobox.setVisible(True)

    @property
    def settings(self):
        s = {
            '__selected__': self.content_combobox.currentText(),
        }
        for name, widget in self._content:
            s[name] = widget.settings
        return s

    @settings.setter
    def settings(self, x):
        selected = x.get('__selected__')
        block = self.content_combobox.blockSignals(True)
        self.content_combobox.clear()
        self.content_combobox.setVisible(bool(selected))
        for idx, (key, widget) in enumerate(self._content):
            self.content_combobox.addItem(key)
            widget.settings = x.get(key, {})
            if selected == key:
                self._on_content_change(idx)
        self.content_combobox.blockSignals(block)


class DurationCheckbox(QtWidgets.QWidget):

    def __init__(self, parent, name, text, sampling_frequency):
        QtWidgets.QWidget.__init__(self, parent)
        self._layout = QtWidgets.QHBoxLayout(self)
        self.checkbox = QtWidgets.QCheckBox(text, self)
        self._layout.addWidget(self.checkbox)
        self.duration = SiValue(self, name, 'time', sampling_frequency)
        self._layout.addWidget(self.duration)
        add_eol_spacer(self._layout)

    @property
    def checked(self):
        return self.checkbox.isChecked()

    @checked.setter
    def checked(self, x):
        self.checkbox.setChecked(bool(x))

    @property
    def value(self):
        return self.duration.value

    @value.setter
    def value(self, x):
        self.duration.value = x

    @property
    def settings(self):
        s = self.duration.settings
        s['enabled'] = self.checkbox.isChecked()
        return s

    @settings.setter
    def settings(self, x):
        self.checkbox.setChecked(bool(x.get('enabled')))
        self.duration.settings = x


class WaitCondition(QtWidgets.QWidget):

    def __init__(self, parent, name, sampling_frequency):
        QtWidgets.QWidget.__init__(self, parent)
        self._layout = QtWidgets.QHBoxLayout(self)
        self._label = QtWidgets.QLabel('Wait for', self)
        self._layout.addWidget(self._label)
        self.duration = SiValue(self, name, 'time', sampling_frequency)
        self.duration.value = 0.5
        self._layout.addWidget(self.duration)
        add_eol_spacer(self._layout)

    @property
    def settings(self):
        return self.duration.settings

    @settings.setter
    def settings(self, x):
        self.duration.settings = x


class ThresholdSubcondition(QtWidgets.QWidget):

    def __init__(self, parent, name, signals, units):
        QtWidgets.QWidget.__init__(self, parent)
        self.setObjectName(name)
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.when_label = QtWidgets.QLabel("When ", self)
        self._layout.addWidget(self.when_label)
        self.signal = QtWidgets.QComboBox(self)
        for signal in signals:
            self.signal.addItem(signal)
        self.signal.currentIndexChanged.connect(self._on_signal_index_changed)
        self._layout.addWidget(self.signal)

        self._operations = ['>', '<', '≥', '≤', '==']
        self.operation = QtWidgets.QComboBox(self)
        for op in self._operations:
            self.operation.addItem(op)
        self._layout.addWidget(self.operation)

        self.threshold = SiValue(self, f'{name}_threshold', 'current', units=units)
        self._layout.addWidget(self.threshold)

    def _on_signal_index_changed(self, index):
        self.threshold.signal_set(self.signal.currentText())

    @property
    def settings(self):
        s = self.threshold.settings
        s['operation'] = self.operation.currentText()
        return s

    @settings.setter
    def settings(self, x):
        op_idx = self._operations.index(x.get('operation', '>'))
        self.signal.setCurrentIndex(self.signal.findText(x.get('signal', 'current')))
        self.operation.setCurrentIndex(op_idx)
        self.threshold.settings = x


class EdgeCondition(QtWidgets.QWidget):

    def __init__(self, parent, name, sampling_frequency, units):
        QtWidgets.QWidget.__init__(self, parent)
        self._layout = QtWidgets.QVBoxLayout(self)

        self.line1 = ThresholdSubcondition(self, f'{name}_threshold', EDGE_SIGNALS, units)
        add_eol_spacer(self.line1.layout())

        self.line2 = QtWidgets.QWidget(self)
        self.line2_layout = QtWidgets.QHBoxLayout(self.line2)
        self.line2_layout.setContentsMargins(0, 0, 0, 0)
        self.line2_label = QtWidgets.QLabel('for at least ', self.line2)
        self.line2_layout.addWidget(self.line2_label)
        self.duration_min = SiValue(self.line2, f'{name}_edge_duration_min', 'time', sampling_frequency)
        self.duration_min.value = 10e-6
        self.line2_layout.addWidget(self.duration_min)
        self.line2_spacer = add_eol_spacer(self.line2_layout)

        self.line3 = QtWidgets.QWidget(self)
        self.line3_layout = QtWidgets.QHBoxLayout(self.line3)
        self.line3_layout.setContentsMargins(0, 0, 0, 0)
        self.line3_checkbox = QtWidgets.QCheckBox('but no more than ', self.line3)
        self.line3_layout.addWidget(self.line3_checkbox)
        self.duration_max = SiValue(self.line3, f'{name}_edge_duration_max', 'time', sampling_frequency)
        self.duration_max.value = 1.0
        self.line3_layout.addWidget(self.duration_max)
        self.line3_spacer = add_eol_spacer(self.line3_layout)

        self._layout.addWidget(self.line1)
        self._layout.addWidget(self.line2)
        self._layout.addWidget(self.line3)

    @property
    def settings(self):
        return {
            'threshold': self.line1.settings,
            'duration_min': self.duration_min.settings,
            'duration_max': self.duration_max.settings,
            'duration_max_enabled': self.line3_checkbox.isChecked(),
        }

    @settings.setter
    def settings(self, x):
        self.line1.settings = x['threshold']
        self.duration_min.settings = x['duration_min']
        self.duration_max.settings = x['duration_max']
        self.line3_checkbox.setChecked(bool(x['duration_max_enabled']))


class WindowCondition(QtWidgets.QWidget):

    def __init__(self, parent, name, sampling_frequency, units):
        QtWidgets.QWidget.__init__(self, parent)
        self._layout = QtWidgets.QVBoxLayout(self)

        self.line1 = ThresholdSubcondition(self, f'{name}_threshold', WINDOW_SIGNALS, units)
        add_eol_spacer(self.line1.layout())

        self.line2 = QtWidgets.QWidget(self)
        self.line2_layout = QtWidgets.QHBoxLayout(self.line2)
        self.line2_layout.setContentsMargins(0, 0, 0, 0)
        self.line2_label1 = QtWidgets.QLabel('over a', self.line2)
        self.line2_layout.addWidget(self.line2_label1)
        self.duration = SiValue(self.line2, f'{name}_duration', 'time', sampling_frequency, units)
        self.line2_layout.addWidget(self.duration)
        self.line2_label2 = QtWidgets.QLabel('window', self.line2)
        self.line2_layout.addWidget(self.line2_label2)

        self.line2_spacer = add_eol_spacer(self.line2_layout)

        self._layout.addWidget(self.line1)
        self._layout.addWidget(self.line2)

    @property
    def settings(self):
        return {
            'threshold': self.line1.settings,
            'duration': self.duration.settings,
        }

    @settings.setter
    def settings(self, x):
        self.line1.settings = x.get('threshold', {'signal': 'energy', 'value': 1})
        self.duration.settings = x.get('duration', {'signal': 'time', 'value': 0.001})


class GpoAction(QtWidgets.QWidget):

    def __init__(self, parent, name):
        QtWidgets.QWidget.__init__(self, parent)
        self.setObjectName(name)
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._enabled = QtWidgets.QCheckBox('Set', self)
        self._layout.addWidget(self._enabled)

        self._signal = QtWidgets.QComboBox(self)
        self._signal.addItem('out0')
        self._signal.addItem('out1')
        self._layout.addWidget(self._signal)

        self._label2 = QtWidgets.QLabel('to', self)
        self._layout.addWidget(self._label2)
        self._value = QtWidgets.QComboBox(self)
        self._value.addItem('0')
        self._value.addItem('1')
        self._layout.addWidget(self._value)

        add_eol_spacer(self._layout)

    @property
    def settings(self):
        return {
            'enabled': self._enabled.isChecked(),
            'signal': self._signal.currentText(),
            'value': self._value.currentIndex(),
        }

    @settings.setter
    def settings(self, x):
        self._enabled.setChecked(bool(x.get('enabled')))
        self._signal.setCurrentIndex(self._signal.findText(x.get('signal', 'out0')))
        self._value.setCurrentIndex(x.get('value', 0))


class StartActions(QtWidgets.QWidget):

    def __init__(self, parent):
        QtWidgets.QWidget.__init__(self, parent)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.ram = QtWidgets.QCheckBox('Capture to RAM buffer')
        self.ram.setChecked(True)
        self.record = QtWidgets.QCheckBox('Record data to file')
        self.gpo = GpoAction(self, 'start_action_gpo')

        self._layout.addWidget(self.ram)
        self._layout.addWidget(self.record)
        self._layout.addWidget(self.gpo)

    @property
    def settings(self):
        return {
            'ram': self.ram.isChecked(),
            'record': self.record.isChecked(),
            'gpo': self.gpo.settings,
        }

    @settings.setter
    def settings(self, x):
        self.ram.setChecked(bool(x['ram']))
        self.record.setChecked(bool(x['record']))
        self.gpo.settings = x.get('gpo', {})


class StopActions(QtWidgets.QWidget):

    def __init__(self, parent):
        QtWidgets.QWidget.__init__(self, parent)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.gpo = GpoAction(self, 'stop_action_gpo')
        self._layout.addWidget(self.gpo)

    @property
    def settings(self):
        return {
            'gpo': self.gpo.settings,
        }

    @settings.setter
    def settings(self, x):
        self.gpo.settings = x.get('gpo', {})


class Trigger(QtWidgets.QWidget):

    def __init__(self, parent, sampling_frequency, units):
        QtWidgets.QWidget.__init__(self, parent)
        self._widgets = {}
        self.setStyleSheet(STYLE_SHEET)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setSpacing(int(self._layout.spacing() * 1.5))
        self._sections = ['before_start', 'start', 'start_actions', 'stop', 'stop_actions', 'after_stop']

        self.before_start = DurationCheckbox(self, 'before_start', 'Before start, capture', sampling_frequency)
        self._layout.addWidget(self.before_start)

        self.start = Section(self, 'Start Condition')
        self._layout.addWidget(self.start)
        self.start.add_body_item('edge', EdgeCondition(self.start.body, 'start_edge', sampling_frequency, units))
        self.start.add_body_item('window', WindowCondition(self.start.body, 'start_window', sampling_frequency, units))

        self.start_actions = Section(self, 'Start Actions')
        self._layout.addWidget(self.start_actions)
        self.start_actions.add_body_item('start_actions', StartActions(self.start_actions.body))

        self.stop = Section(self, 'Stop Condition')
        self._layout.addWidget(self.stop)
        self.stop.add_body_item('wait', WaitCondition(self.stop.body, 'stop_duration', sampling_frequency))
        self.stop.add_body_item('edge', EdgeCondition(self.stop.body, 'stop_edge', sampling_frequency, units))
        self.stop.add_body_item('window', WindowCondition(self.stop.body, 'stop_window', sampling_frequency, units))

        self.stop_actions = Section(self, 'Stop Actions')
        self._layout.addWidget(self.stop_actions)
        self.stop_actions.add_body_item('stop_actions', StopActions(self.stop_actions.body))

        self.after_stop = DurationCheckbox(self, 'after_stop', 'After stop, capture', sampling_frequency)
        self._layout.addWidget(self.after_stop)

        self._vertical_spacer = QtWidgets.QSpacerItem(40, 20,
                                       QtWidgets.QSizePolicy.Minimum,
                                       QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._vertical_spacer)

    @property
    def settings(self):
        s = {}
        for section in self._sections:
            s[section] = getattr(getattr(self, section), 'settings')
        return s

    @settings.setter
    def settings(self, x):
        if x is None:
            x = TRIGGER_SETTINGS_DEFAULT
        for section in self._sections:
            setattr(getattr(self, section), 'settings', x.get(section, {}))


if __name__ == '__main__':
    import json
    import ctypes
    if sys.platform.startswith('win'):
        ctypes.windll.user32.SetProcessDPIAware()
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    app = QtWidgets.QApplication(sys.argv)
    dialog = QtWidgets.QDialog()
    layout = QtWidgets.QVBoxLayout()
    w = Trigger(dialog, 2000000, {'energy': 'J', 'charge': 'C'})
    w.settings = None  # defaults
    layout.addWidget(w)
    dialog.setLayout(layout)
    dialog.exec_()
    print(json.dumps(w.settings, indent=4))
