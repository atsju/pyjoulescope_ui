# Copyright 2022-2023 Jetperch LLC
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

from joulescope_ui.capabilities import CAPABILITIES
from .device import Device
from joulescope_ui import N_, get_topic_name
from joulescope_ui.metadata import Metadata
import copy
import queue
import threading


def _version_u32_to_str(v):
    major = (v >> 24) & 0xff
    minor = (v >> 16) & 0xff
    patch = (v & 0xffff)
    return '.'.join(str(x) for x in [major, minor, patch])


EVENTS = {
    'statistics/!data': Metadata('obj', 'Periodic statistics data for each signal.'),
}

SETTINGS = {
    'name': {
        'dtype': 'str',
        'brief': N_('Device name'),
        'detail': N_("""\
        The Joulescope UI automatically populates the device name
        with the device type and serial number.
        
        This setting allows you to change the default, if you wish, to better
        reflect how you are using your JS220.  This setting is
        most useful when you are instrumenting a system using 
        multiple Joulescopes."""),
        'default': None,
    },
    'info': {
        'dtype': 'obj',
        'brief': N_('Device information'),
        'default': None,
        'flags': ['ro', 'hidden'],
    },
    'state': {
        'dtype': 'int',
        'brief': N_('Device state indicator'),
        'options': [
            [0, 'closed'],
            [1, 'opening'],
            [2, 'open'],
            [3, 'closing'],
        ],
        'default': 0,
        'flags': ['ro', 'hidden'],
    },
    'state_req': {
        'dtype': 'int',
        'brief': N_('Requested device state'),
        'options': [
            [0, 'closed'],
            [1, 'open'],
        ],
        'default': 1,
        'flags': ['ro', 'hidden'],
    },
    'sources/1/name': {
        'dtype': 'str',
        'brief': N_('Device name'),
        'default': None,
        'flags': ['ro', 'hidden'],  # duplicated from settings/name
    },
    'sources/1/info': {
        'dtype': 'obj',
        'brief': N_('Device information'),
        'default': None,
        'flags': ['ro', 'hidden'],  # duplicated from settings/info['device']
    },
    'signal_frequency': {
        'dtype': 'int',
        'brief': N_('Signal frequency'),
        'detail': N_("""\
        This setting controls the output sampling frequency for the 
        measurement signals current, voltage, and power.  Use this
        setting to reduce the data storage requirements for long
        captures where lower temporal accuracy is sufficient. 
        
        The JS220 instrument always samples at 2 MHz and 
        then downsamples to 1 MHz.  This setting controls 
        additional optional downsampling."""),
        'options': [
            [1000000, "1 MHz"],
            [500000, "500 kHz"],
            [200000, "200 kHz"],
            [100000, "100 kHz"],
            [50000, "50 kHz"],
            [20000, "20 kHz"],
            [10000, "10 kHz"],
            [5000, "5 kHz"],
            [2000, "2 kHz"],
            [1000, "1 kHz"],
            [500, "500 Hz"],
            [200, "200 Hz"],
            [100, "100 Hz"],
            [50, "50 Hz"],
            [20, "20 Hz"],
            [10, "10 Hz"],
            [5, "5 Hz"],
            [2, "2 Hz"],
            [1, "1 Hz"],
        ],
        'default': 1_000_000,
    },
    'statistics_frequency': {
        'dtype': 'int',
        'brief': N_('Statistics frequency'),
        'detail': N_("""\
            This setting controls the output frequency for 
            the statistics data that is displayed in the
            multimeter and value widgets.  Statistics data
            is computed over the full rate 1 MHz samples."""),
        'options': [
            [100, '100 Hz'],
            [50, '50 Hz'],
            [20, '20 Hz'],
            [10, '10 Hz'],
            [5, '5 Hz'],
            [2, '2 Hz'],
            [1, '1 Hz'],
        ],
        'default': 2,
    },
    'target_power': {
        'dtype': 'bool',
        'brief': N_('Target power'),
        'detail': N_("""\
            Toggle the connection between the current terminals.
            
            When enabled, current flows between the current terminals.
            When disabled, current cannot flow between the current terminals.
            In common system setups, this inhibits target power, which can
            be used to power cycle reset the target device."""),
        'default': True,
        'flags': ['hidden'],   # Display in ExpandingWidget's header_ex_widget
    },
    'current_range': {
        'dtype': 'int',
        'brief': N_('Current range'),
        'detail': N_("""\
            Configure the JS220's current range.  Most applications should
            use the default, "auto".
            
            Use the other manual settings with care.  It is very easy to
            configure a setting that saturates, which will ignore regions
            of current draw larger than the current range setting."""),
        'options': [
            [-1, 'auto'],
            [129, '10 A'],
            [130, '180 mA'],
            [132, '18 mA'],
            [136, '1.8 mA'],
            [144, '180 µA'],
            [160, '18 µA'],
        ],
        'default': -1,  # auto
    },
    # current range min
    # current range max
    'voltage_range': {
        'dtype': 'int',
        'brief': N_('Voltage range'),
        'detail': N_("""\
            Configure the JS220's voltage range.  Most applications should
            use the default, "auto"."""),
        'options': [
            # [-1, 'auto'],
            [0, '15 V'],
            [1, '2 V'],
        ],
        'default': 0,   # todo -1,
    },
    'trigger_dir': {
        'dtype': 'int',
        'brief': N_('Trigger direction'),
        'detail': N_("""\
            Configure the direction of the JS220's trigger BNC connection.
            
            0 (default) configures the BNC trigger for input only.
            The BNC connection is high-impedance.
            
            1 configures the BNC trigger for output.  The BNC connection
            has 50 Ohm output impedance.
            
            In both cases, the trigger input signal is valid, which
            enables internal inspection and recording of the trigger output.
        """),
        'options': [
            [0, 'input'],
            [1, 'output'],
        ],
        'default': 0,  # input
    },
    'gpio_voltage': {
        'dtype': 'int',
        'brief': N_('GPIO voltage'),
        'detail': N_("""\
            Configure the JS220's reference voltage for the general-purpose
            inputs and outputs.
            
            We recommend using "Vref" when attaching
            general-purpose outputs (GPO) to other equipment.  Using Vref
            prevents the GPO from backpowering target devices when they
            powered down.  The Vref signal and general-purpose inputs
            are all extremely high impedance to minimize leakage currents.
            
            "3.3 V" uses an internally-generated 3.3V reference voltage."""),
        'options': [
            [0, 'Vref'],
            [1, '3.3 V'],
        ],
        'default': 0,  # Vref
    },
    'out/0': {
        'dtype': 'bool',
        'brief': N_('GPO 0 output value'),
        'detail': N_('Turn the general-purpose output 0 on or off.'),
        'default': False,
    },
    'out/1': {
        'dtype': 'bool',
        'brief': N_('GPO 1 output value'),
        'detail': N_('Turn the general-purpose output 1 on or off.'),
        'default': False,
    },
    'out/T': {
        'dtype': 'bool',
        'brief': N_('Trigger output value'),
        'detail': N_("""Turn the trigger output on or off.
        
            The trigger must also be configured for output for this
            setting to have any effect."""),
        'default': False,
    },
}


_SETTINGS_MAP = {
    'signal_frequency': 'h/fs',

}


_SIGNALS = {
    'i': {
        'name': 'current',
        'dtype': 'f32',
        'units': 'A',
        'brief': N_('Current'),
        'detail': N_("""Enable the current signal streaming."""),
        'default': True,
        'topics': ('s/i/ctrl', 's/i/!data'),
    },
    'v': {
        'name': 'voltage',
        'dtype': 'f32',
        'units': 'V',
        'brief': N_('Voltage'),
        'detail': N_("""Enable the voltage signal streaming."""),
        'default': True,
        'topics': ('s/v/ctrl', 's/v/!data'),
    },
    'p': {
        'name': 'power',
        'dtype': 'f32',
        'units': 'W',
        'brief': N_('Power'),
        'detail': N_("""Enable the power signal streaming."""),
        'default': True,
        'topics': ('s/p/ctrl', 's/p/!data'),
    },
    'r': {
        'name': 'current range',
        'dtype': 'u8',
        'units': '',
        'brief': N_('Current Range'),
        'detail': N_("""\
            Enable the streaming for the selected current range.
    
            The current range is useful for understanding how your Joulescope
            autoranges to measure your current signal.  It can also be helpful
            in separating target system behavior from the small current range
            switching artifacts."""),
        'default': False,
        'topics': ('s/i/range/ctrl', 's/i/range/!data'),

    },
    '0': {
        'name': 'gpi[0]',
        'dtype': 'u1',
        'units': '',
        'brief': N_('GPI 0'),
        'detail': N_('Enable the general purpose input 0 signal streaming.'),
        'default': False,
        'topics': ('s/gpi/0/ctrl', 's/gpi/0/!data'),
    },
    '1': {
        'name': 'gpi[1]',
        'dtype': 'u1',
        'units': '',
        'brief': N_('GPI 1'),
        'detail': N_('Enable the general purpose input 1 signal streaming.'),
        'default': False,
        'topics': ('s/gpi/1/ctrl', 's/gpi/1/!data'),
    },
    '2': {
        'name': 'gpi[2]',
        'dtype': 'u1',
        'units': '',
        'brief': N_('GPI 2'),
        'detail': N_('Enable the general purpose input 2 signal streaming.'),
        'default': False,
        'topics': ('s/gpi/2/ctrl', 's/gpi/2/!data'),
    },
    '3': {
        'name': 'gpi[3]',
        'dtype': 'u1',
        'units': '',
        'brief': N_('GPI 3'),
        'detail': N_('Enable the general purpose input 3 signal streaming.'),
        'default': False,
        'topics': ('s/gpi/3/ctrl', 's/gpi/3/!data'),
    },
    'T': {
        'name': 'trigger_in',
        'dtype': 'u1',
        'units': '',
        'brief': N_('Trigger input'),
        'detail': N_('Enable the trigger input signal streaming.'),
        'default': False,
        'topics': ('s/gpi/7/ctrl', 's/gpi/7/!data'),
    },
}


_GPO_BIT = {
    '0': 1 << 0,
    '1': 1 << 1,
    'T': 1 << 7,
}


def _populate():
    global SETTINGS, EVENTS
    for signal_id, value in _SIGNALS.items():
        SETTINGS[f'signals/{signal_id}/name'] = {
            'dtype': 'str',
            'brief': N_('Signal name'),
            'flags': ['hidden'],
            'default': value['brief'],
        }
        SETTINGS[f'signals/{signal_id}/enable'] = {
            'dtype': 'bool',
            'brief': value['brief'],
            'detail': value['detail'],
            'flags': ['hidden'],
            'default': value['default'],
        }
        EVENTS[f'signals/{signal_id}/!data'] = Metadata('obj', 'Signal data')


_populate()


class Js220(Device):

    SETTINGS = SETTINGS

    def __init__(self, driver, device_path, unique_id):
        super().__init__(driver, device_path, unique_id)
        self.EVENTS = copy.deepcopy(EVENTS)
        self.SETTINGS = copy.deepcopy(SETTINGS)
        self.SETTINGS['name']['default'] = device_path
        self._info = {
            'device': {
                'vendor': 'Jetperch LLC',
                'model': 'JS220',
                'serial_number': device_path.split('/')[-1],
            },
            'versions': None,
        }
        self.SETTINGS['info']['default'] = self._info
        self.SETTINGS['sources/1/name']['default'] = device_path
        self.SETTINGS['sources/1/info']['default'] = self._info['device']

        self._statistics_offsets = None
        self._on_settings_fn = self._on_settings
        for key, value in _SIGNALS.items():
            self._signal_forward(key, value['topics'][1], unique_id)
        self._on_target_power_app_fn = self._on_target_power_app
        self._pubsub.subscribe('registry/app/settings/target_power', self._on_target_power_app_fn, ['pub', 'retain'])

        self._on_stats_fn = self._on_stats  # for unsub
        self._thread = None
        self._quit = False
        self._target_power_app = False
        self._queue = queue.Queue()

    def signal_subtopics(self, signal_id, topic_type):
        """Query the signal topics.

        :param signal_id: The signal id, such as 'i'.
        :param topic_type: The topic type to get, one of ['ctrl', 'data'].
        :return: The subtopic for this device.
        """
        s = _SIGNALS[signal_id]
        topics = s['topics']
        if topic_type == 'ctrl':
            return topics[0]
        elif topic_type == 'data':
            return topics[1]
        raise ValueError(f'unsupported topic_type {topic_type}')

    def _signal_forward(self, signal_id, dtopic, unique_id):
        utopic = f'events/signals/{signal_id}/!data'
        t = f'{get_topic_name(unique_id)}/{utopic}'
        self._pubsub.topic_add(t, Metadata('obj', 'signal'), exists_ok=True)
        self._driver_subscribe(dtopic, ['pub'], self._signal_forward_factory(signal_id, t))

    def _signal_forward_factory(self, signal_id, utopic):
        signal_info = _SIGNALS[signal_id]
        dtype = signal_info['dtype']
        field = signal_info['name']
        units = signal_info['units']
        def fn(dtopic, value):
            fwd = {
                'source': self._info['device'],
                'sample_id': value['sample_id'] // value['decimate_factor'],
                'sample_freq': value['sample_rate'] // value['decimate_factor'],
                'time': None,  # todo
                'field': field,
                'data': value['data'],
                'dtype': dtype,
                'units': units,
                'origin_sample_id': value['sample_id'],
                'orig_sample_freq': value['sample_rate'],
                'orig_decimate_factor': value['decimate_factor'],
            }
            self._pubsub.publish(utopic, fwd)
        return fn

    def _send_to_thread(self, cmd, args=None):
        self._queue.put((cmd, args), block=False)

    def finalize(self):
        self.on_action_finalize()
        self._pubsub.unsubscribe('registry/app/settings/target_power', self._on_target_power_app_fn)
        super().finalize()

    def _open_req(self):
        # must be called from UI pubsub thread
        if self._thread is not None and self._ui_query('settings/state') == 3:
            self._close_req()
        if self._thread is None:
            self._log.info('open req start')
            try:
                while True:
                    self._queue.get(block=False)
            except queue.Empty:
                pass  # done!
            self._ui_publish('settings/state', 'opening')
            self._quit = False
            self._thread = threading.Thread(target=self._run)
            self._thread.start()
            self._log.info('open req done')

    def _close_req(self):
        # must be called from UI pubsub thread
        if self._thread is not None:
            self._log.info('closing')
            self._ui_publish('settings/state', 'closing')
            self._send_to_thread('close')
            self._quit = True
            self._thread.join()
            self._thread = None
            self._ui_publish('settings/state', 'closed')
            self._log.info('closed')

    def on_action_finalize(self):
        self._log.info('finalize')
        self._close_req()

    def _run_cmd_settings(self, topic, value):
        self._log.info(f'setting(%s): %s <= %s', self, topic, value)
        if topic.endswith('/enable'):
            signal_id = topic.split('/')[1]
            t = _SIGNALS[signal_id]['topics'][0]
            if t is not None:
                self._driver_publish(t, bool(value))
            else:
                self._log.warning('invalid enable: %s', topic)
        elif topic.startswith('out/'):
            v = _GPO_BIT[topic[4:]]
            t = 's/gpo/+/!set' if bool(value) else 's/gpo/+/!clr'
            self._driver_publish(t, v)
        elif topic == 'signal_frequency':
            self._driver_publish('h/fs', int(value))
        elif topic == 'statistics_frequency':
            scnt = 1_000_000 // value
            self._driver_publish('s/stats/scnt', scnt)
        elif topic == 'target_power':
            self._current_range_update()
        elif topic == 'current_range':
            self._current_range_update()
        elif topic == 'voltage_range':
            if value == -1:
                self._driver_publish('s/v/range/mode', 'auto')
            else:
                self._driver_publish('s/v/range/mode', 'manual')
                self._driver_publish('s/v/range/select', value)
        elif topic == 'trigger_dir':
            self._driver_publish('c/trigger/dir', value)
        elif topic == 'gpio_voltage':
            self._driver_publish('c/gpio/vref', value)
        elif topic == 'name':
            self._ui_publish('settings/sources/1/name', value)
        elif topic in ['info', 'state', 'state_req', 'out', 'enable',
                       'sources', 'sources/1', 'sources/1/info', 'sources/1/name',
                       'signals']:
            pass
        elif topic.startswith('signals/'):
            pass
        else:
            self._log.warning('Unsupported topic %s', f'{get_topic_name(self)}/settings/{topic}')

    def _current_range_update(self):
        if self._target_power_app and self.target_power:
            if self.current_range == -1:
                self._log.info('current_range auto')
                self._driver_publish('s/i/range/mode', 'auto')
            else:
                self._log.info('current_range manual %s', self.current_range)
                self._driver_publish('s/i/range/select', self.current_range)
                self._driver_publish('s/i/range/mode', 'manual')
        else:
            self._log.info('current_range off')
            self._driver_publish('s/i/range/mode', 'off')

    def _run_cmd(self, cmd, args):
        if cmd == 'settings':
            self._run_cmd_settings(*args)
        elif cmd == 'current_range_update':
            self._current_range_update()
        elif cmd == 'close':
            pass  # handled in outer wrapper
        else:
            self._log.warning('Unhandled cmd: %s', cmd)

    def _run(self):
        self._log.info('thread start')
        if self._open():
            self._log.info('thread exit due to open fail')
            return 1
        self._ui_publish('settings/state', 'open')
        self._log.info('thread open complete')
        while not self._quit:
            try:
                cmd, args = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if cmd == 'close':
                break
            self._run_cmd(cmd, args)
        self._close()
        self._log.info('thread stop')
        return 0

    def _open(self):
        self._log.info('open start')
        try:
            self._driver.open(self._path, 'restore')
        except Exception:
            self._log.warning('driver open failed')
            self._ui_publish('settings/state', 'closing')
            return 1
        try:
            self._info['versions'] = {
                'hw': str(self._driver_query('c/hw/version') >> 24),
                'fw': _version_u32_to_str(self._driver_query('c/fw/version')),
                'fpga': _version_u32_to_str(self._driver_query('s/fpga/version')),
            }
            self._ui_publish('settings/info', self._info)
            self._driver_publish('s/stats/ctrl', 1)
            self._driver_subscribe('s/stats/value', 'pub', self._on_stats_fn)
            self._ui_subscribe('settings', self._on_settings_fn, ['pub', 'retain'])
        except Exception:
            self._log.exception('driver config failed')
            self._ui_publish('settings/state', 'closing')
            return 1
        self._log.info('open %s done', self.unique_id)
        return 0

    def _close(self):
        if self.state == 0:  # already closed
            return
        self._log.info('close %s start', self.unique_id)
        self._ui_unsubscribe('settings', self._on_settings_fn)
        self._ui_publish('settings/state', 'closing')
        self._driver_unsubscribe('s/stats/value', self._on_stats_fn)
        try:
            for t in _SIGNALS.values():
                self._driver_publish(t['topics'][0], 0)
            self._driver_publish('s/stats/ctrl', 0)
        except RuntimeError as ex:
            self._log.info('Exception during close cleanup: %s', ex)
        self._driver.close(self._path)
        self._log.info('close %s done', self.unique_id)

    def _on_stats(self, topic, value):
        if self._statistics_offsets is None:
            accum_sample_start = value['time']['accum_samples']['value'][-1]
            charge = value['accumulators']['charge']['value']
            energy = value['accumulators']['energy']['value']
            self._statistics_offsets = [accum_sample_start, charge, energy]
        accum_sample_start, charge, energy = self._statistics_offsets
        value['time']['accum_samples']['value'][0] = accum_sample_start
        value['accumulators']['charge']['value'] -= charge
        value['accumulators']['energy']['value'] -= energy
        value['source'] = {
            'unique_id': self.unique_id,
        }
        self._ui_publish('events/statistics/!data', value)

    def on_setting_state_req(self, value):
        if value == 0:
            self._close_req()
        else:
            self._open_req()

    def _on_settings(self, topic, value):
        if self._thread is None:
            return
        t = f'{get_topic_name(self)}/settings/'
        if not topic.startswith(t):
            if topic != t[:-1]:
                self._log.warning('Invalid settings topic %s', topic)
            return
        topic = topic[len(t):]
        self._send_to_thread('settings', (topic, value))

    def _on_target_power_app(self, value):
        self._target_power_app = bool(value)
        self._send_to_thread('current_range_update', None)

    def on_action_accum_clear(self, topic, value):
        prev_value = self._statistics_offsets
        if value is None:
            self._statistics_offsets = None
        else:
            self._statistics_offsets = list(value)
        return topic, prev_value
