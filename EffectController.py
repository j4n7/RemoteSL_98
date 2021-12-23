from __future__ import absolute_import, print_function, unicode_literals
from builtins import str
from builtins import range
from builtins import object

from past.utils import old_div
import Live
import json

from .RemoteSLComponent import RemoteSLComponent
from .consts import *
from _Generic.Devices import *


class EffectController(RemoteSLComponent):
    u"""Representing the 'left side' of the RemoteSL:
    The upper two button rows with the encoders, and the row with the poties and drum pads.

    Only the First Button row with the Encoders are handled by this script. The rest will
    be forwarded to Live, so that it can be freely mapped with the RemoteMapper.

    The encoders and buttons are used to control devices in Live, by attaching to
    the selected one in Live, when the selection is not locked...
    Switching through more than 8 parameters is done by pressing the up/down bottons next
    to the left display. This will then shift the selected parameters by 8.
    """

    def __init__(self, remote_sl_parent, display_controller):
        RemoteSLComponent.__init__(self, remote_sl_parent)
        self.__display_controller = display_controller
        self.__parent = remote_sl_parent
        self.__selected_track = None
        self.__selected_track_index = None
        self.__assigned_device = None
        self.__assigned_device_index = None
        self.__assigned_device_is_locked = False
        self.__transport_locked = False
        self.__change_assigned_device(self.__parent.song().appointed_device)
        self.__bank = 0
        self.__show_bank = False
        self.__strips = [EffectChannelStrip(self, x)
                         for x in range(NUM_CONTROLS_PER_ROW)]
        self.song().view.add_selected_track_listener(self.__device_changed)
        self.__reassign_strips()

    def disconnect(self):
        self.__change_assigned_device(None)

    def remote_sl_parent(self):
        return self.__parent

    def remote_sl_selected_track(self):
        return self.__selected_track

    def remote_sl_selected_track_index(self):
        return self.__selected_track_index

    def remote_sl_assigned_device(self):
        return self.__assigned_device

    def remote_sl_assigned_device_index(self):
        return self.__assigned_device_index

    def remote_sl_transport_locked(self):
        return self.__transport_locked

    def remote_sl_reassign_strips(self):
        return self.__reassign_strips()

    def remote_sl_count(self):
        return self.__count()

    def receive_midi_cc(self, cc_no, cc_value):
        if cc_no in fx_display_button_ccs:
            self.__handle_param_page_up_down_ccs(cc_no, cc_value)
        elif cc_no in fx_select_button_ccs:
            self.__handle_select_button_ccs(cc_no, cc_value)
        elif cc_no in fx_upper_button_row_ccs:
            strip = self.__strips[cc_no - FX_UPPER_BUTTON_ROW_BASE_CC]
            if cc_value == CC_VAL_BUTTON_PRESSED:
                strip.on_upper_button_pressed()
        elif cc_no in fx_lower_button_row_ccs:
            if FX_LOWER_BUTTON_ROW_DEVICE:
                strip = self.__strips[cc_no - FX_LOWER_BUTTON_ROW_BASE_CC]
                if cc_value == 127:
                    strip.on_lower_button_pressed()
            else:
                assert False, u'Lower Button CCS should be passed to Live!'
        elif cc_no in fx_encoder_row_ccs:
            strip = self.__strips[cc_no - FX_ENCODER_ROW_BASE_CC]
            strip.on_encoder_moved(cc_value)
        elif cc_no in ts_ccs:
            self.__handle_transport_ccs(cc_no, cc_value)
        elif cc_no in mx_display_button_ccs:
            self.__handle_device_page_up_down_ccs(cc_no, cc_value)
        elif cc_no in fx_poti_row_ccs:
            assert False, u'Poti CCS should be passed to Live!'
        else:
            assert False, u'unknown FX midi message'

    def receive_midi_note(self, note, velocity):
        if note in fx_drum_pad_row_notes:
            assert False, u'DrumPad CCS should be passed to Live!'
        else:
            assert False, u'unknown FX midi message'

    def build_midi_map(self, script_handle, midi_map_handle):
        needs_takeover = True
        for s in self.__strips:
            strip_index = self.__strips.index(s)
            cc_no = fx_encoder_row_ccs[strip_index]
            if s.assigned_parameter():
                map_mode = Live.MidiMap.MapMode.relative_smooth_signed_bit
                parameter = s.assigned_parameter()
                if self.support_mkII():
                    feedback_rule = Live.MidiMap.CCFeedbackRule()
                    feedback_rule.cc_no = fx_encoder_feedback_ccs[strip_index]
                    feedback_rule.channel = SL_MIDI_CHANNEL
                    feedback_rule.delay_in_ms = 0
                    feedback_rule.cc_value_map = tuple(
                        [int(1.5 + old_div(float(index), 127.0) * 10.0) for index in range(128)])
                    ring_mode_value = FX_RING_VOL_VALUE
                    if parameter.min == -1 * parameter.max:
                        ring_mode_value = FX_RING_PAN_VALUE
                    else:
                        if parameter.is_quantized:
                            ring_mode_value = FX_RING_SIN_VALUE
                    if FX_ENCODER_ON_DEVICE_ACTIVE:
                        if self.__assigned_device.is_active:
                            self.send_midi(
                                (self.cc_status_byte(), fx_encoder_led_mode_ccs[strip_index], ring_mode_value))
                            Live.MidiMap.map_midi_cc_with_feedback_map(
                                midi_map_handle, parameter, SL_MIDI_CHANNEL, cc_no, map_mode, feedback_rule, not needs_takeover)
                            Live.MidiMap.send_feedback_for_parameter(
                                midi_map_handle, parameter)
                    else:
                        self.send_midi(
                            (self.cc_status_byte(), fx_encoder_led_mode_ccs[strip_index], ring_mode_value))
                        Live.MidiMap.map_midi_cc_with_feedback_map(
                            midi_map_handle, parameter, SL_MIDI_CHANNEL, cc_no, map_mode, feedback_rule, not needs_takeover)
                        Live.MidiMap.send_feedback_for_parameter(
                            midi_map_handle, parameter)
                else:
                    Live.MidiMap.map_midi_cc(
                        midi_map_handle, parameter, SL_MIDI_CHANNEL, cc_no, map_mode, not needs_takeover)
            else:
                if self.support_mkII():
                    self.send_midi((
                        self.cc_status_byte(), fx_encoder_led_mode_ccs[strip_index], 0))
                    self.send_midi((
                        self.cc_status_byte(), fx_encoder_feedback_ccs[strip_index], 0))
                Live.MidiMap.forward_midi_cc(
                    script_handle, midi_map_handle, SL_MIDI_CHANNEL, cc_no)

        for cc_no in fx_forwarded_ccs + ts_ccs:
            Live.MidiMap.forward_midi_cc(
                script_handle, midi_map_handle, SL_MIDI_CHANNEL, cc_no)

        for note in fx_forwarded_notes:
            Live.MidiMap.forward_midi_note(
                script_handle, midi_map_handle, SL_MIDI_CHANNEL, note)

    def refresh_state(self):
        self.__update_select_row_leds()
        self.__reassign_strips()

    def __reassign_strips(self):
        self.__selected_track = self.__parent.song().view.selected_track
        for n, track in enumerate(self.__parent.song().tracks):
            if track == self.__selected_track:
                self.__selected_track_index = n
                break
        devices = self.__selected_track.devices
        assigned_device_parent_type = None
        if self.__assigned_device:
            assigned_device_parent_type = type(
                self.__assigned_device.canonical_parent).__name__
            if assigned_device_parent_type == 'Chain' or assigned_device_parent_type == 'DrumChain':
                assigned_device = self.__assigned_device.canonical_parent.canonical_parent
            else:
                assigned_device = self.__assigned_device
            for n, device in enumerate(devices):
                if device == assigned_device:
                    self.__assigned_device_index = n
                    break
        else:
            self.__assigned_device_index = None

        if FX_LOWER_BUTTON_ROW_DEVICE:
            if FX_LOWER_BUTTON_ROW_DEVICE_ALL:
                for n in range(NUM_CONTROLS_PER_ROW):
                    if n < len(devices):
                        self.send_midi(
                            (self.cc_status_byte(), FX_LOWER_BUTTON_ROW_BASE_CC + n, 1))
                    else:
                        self.send_midi(
                            (self.cc_status_byte(), FX_LOWER_BUTTON_ROW_BASE_CC + n, 0))
            else:
                for n in range(NUM_CONTROLS_PER_ROW):
                    if n < len(devices) and self.__assigned_device:
                        if assigned_device_parent_type == 'Chain' or assigned_device_parent_type == 'DrumChain':
                            device = self.__assigned_device.canonical_parent.canonical_parent
                        else:
                            device = self.__assigned_device
                        if device == devices[n]:
                            self.send_midi(
                                (self.cc_status_byte(), FX_LOWER_BUTTON_ROW_BASE_CC + n, 1))
                        else:
                            self.send_midi(
                                (self.cc_status_byte(), FX_LOWER_BUTTON_ROW_BASE_CC + n, 0))
                    else:
                        self.send_midi(
                            (self.cc_status_byte(), FX_LOWER_BUTTON_ROW_BASE_CC + n, 0))

            # self.log('', f'·[TRACK] {self.__selected_track.name}')
            # if self.__assigned_device:
            #     self.log(f'[DEVICE] {self.__assigned_device.name}')

        if self.__transport_locked:
            for n in range(NUM_CONTROLS_PER_ROW):
                if n < self.__count():
                    self.send_midi(
                        (self.cc_status_byte(), FX_UPPER_BUTTON_ROW_BASE_CC + n, 1))
                else:
                    self.send_midi(
                        (self.cc_status_byte(), FX_UPPER_BUTTON_ROW_BASE_CC + n, 0))
        else:
            for n in range(8):
                self.send_midi(
                    (self.cc_status_byte(), FX_UPPER_BUTTON_ROW_BASE_CC + n, 0))

        page_up_value = CC_VAL_BUTTON_RELEASED
        page_down_value = CC_VAL_BUTTON_RELEASED
        if self.__assigned_device:
            param_index = 0
            param_banks = 0
            chosen_bank = 0
            param_names = []
            parameters = []
            if FX_ENCODER_MORE_PARAMETERS:
                chosen_bank = True
            else:
                if list(DEVICE_DICT.keys()).count(self.__assigned_device.class_name) > 0:
                    param_banks = DEVICE_DICT[self.__assigned_device.class_name]
                    chosen_bank = param_banks[self.__bank]
            for s in self.__strips:
                param = None
                name = u''
                if chosen_bank:
                    if FX_ENCODER_MORE_PARAMETERS:
                        if param_index + 8 * self.__bank < len(self.__assigned_device.parameters[1:]):
                            param = self.__assigned_device.parameters[1:][param_index + 8 * self.__bank]
                        else:
                            param = None
                    else:
                        param = get_parameter_by_name(
                            self.__assigned_device, chosen_bank[param_index])
                else:
                    new_index = param_index + 8 * self.__bank
                    device_parameters = self.__assigned_device.parameters[1:]
                    if new_index < len(device_parameters):
                        param = device_parameters[new_index]
                if param:
                    name = param.name
                s.set_assigned_parameter(param)
                parameters.append(param)
                param_names.append(name)
                param_index += 1

            if self.support_mkII() and FX_ENCODER_ON_DEVICE_ACTIVE:
                if not self.__assigned_device.is_active:
                    for s in self.__strips:
                        strip_index = self.__strips.index(s)
                        self.send_midi(
                            (self.cc_status_byte(), fx_encoder_led_mode_ccs[strip_index], 0))
                        self.send_midi(
                            (self.cc_status_byte(), fx_encoder_feedback_ccs[strip_index], 0))

            if self.__bank > 0:
                page_down_value = CC_VAL_BUTTON_PRESSED
            if self.__bank + 1 < self.__number_of_parameter_banks(self.__assigned_device,
                                                                  more=FX_ENCODER_MORE_PARAMETERS):
                page_up_value = CC_VAL_BUTTON_PRESSED
            self.__report_bank()
        else:
            for s in self.__strips:
                s.set_assigned_parameter(None)

            param_names = [u'Please select a Device in Live to edit it...']
            parameters = [None for x in range(NUM_CONTROLS_PER_ROW)]
        self.__display_controller.setup_left_display(param_names, parameters)
        self.request_rebuild_midi_map()

        if self.support_mkII():
            self.send_midi(
                (self.cc_status_byte(), FX_DISPLAY_PAGE_DOWN, page_down_value))
            self.send_midi(
                (self.cc_status_byte(), FX_DISPLAY_PAGE_UP, page_up_value))

            if MX_DISPLAY_PAGE_DEVICE_CHILDS:
                page_up_value = CC_VAL_BUTTON_RELEASED
                page_down_value = CC_VAL_BUTTON_RELEASED
                if assigned_device_parent_type == 'Chain' or assigned_device_parent_type == 'DrumChain':
                    rack_device = self.__assigned_device.canonical_parent.canonical_parent
                    if rack_device.chains and len(rack_device.chains) > 1:
                        selected_chain = rack_device.view.selected_chain
                        selected_chain_index = list(
                            rack_device.chains).index(selected_chain)
                        if selected_chain_index > 0:
                            page_down_value = CC_VAL_BUTTON_PRESSED
                        if selected_chain_index < len(rack_device.chains) - 1:
                            page_up_value = CC_VAL_BUTTON_PRESSED
                        self.send_midi(
                            (self.cc_status_byte(), MX_DISPLAY_PAGE_UP, page_up_value))
                        self.send_midi(
                            (self.cc_status_byte(), MX_DISPLAY_PAGE_DOWN, page_down_value))

                        self.send_midi(
                            (self.cc_status_byte(), FX_SELECT_LOWER_BUTTON_ROW, 1))

                else:
                    self.send_midi(
                        (self.cc_status_byte(), MX_DISPLAY_PAGE_UP, page_up_value))
                    self.send_midi(
                        (self.cc_status_byte(), MX_DISPLAY_PAGE_DOWN, page_down_value))

                    self.send_midi(
                        (self.cc_status_byte(), FX_SELECT_LOWER_BUTTON_ROW, 0))

    def __count(self):
        assigned_device_parent = self.__assigned_device.canonical_parent
        assigned_device_parent_type = type(
            self.__assigned_device.canonical_parent).__name__

        assigned_device_chain_n = None
        if assigned_device_parent_type == 'Chain' or assigned_device_parent_type == 'DrumChain':
            rack_device = self.__assigned_device.canonical_parent.canonical_parent
            for n, chain in enumerate(rack_device.chains):
                if chain == assigned_device_parent:
                    # Make a string, otherwise None = 0
                    assigned_device_chain_n = str(n)
        count = 0
        for n in range(8):
            if assigned_device_chain_n:
                snapshot_key = f'{str(self.__assigned_device_index)}_{assigned_device_chain_n}_{str(n)}'
            else:
                snapshot_key = f'{str(self.__assigned_device_index)}_{str(n)}'
            snapshot_data = self.__selected_track.get_data(snapshot_key, None)
            if snapshot_data:
                count += 1
            else:
                return count

    def __number_of_parameter_banks(self, device, more=False):
        if more:
            def ceil(number):
                return int(number) + (number % 1 > 0)

            return ceil(len(list(device.parameters)) / 8)
        else:
            return number_of_parameter_banks(device)

    def __handle_param_page_up_down_ccs(self, cc_no, cc_value):
        if self.__assigned_device:
            new_bank = self.__bank
            if cc_value == CC_VAL_BUTTON_PRESSED:
                if cc_no == FX_DISPLAY_PAGE_UP:
                    new_bank = min(
                        self.__bank + 1, self.__number_of_parameter_banks(self.__assigned_device, 
                                                                          more=FX_ENCODER_MORE_PARAMETERS) - 1)
                elif cc_no == FX_DISPLAY_PAGE_DOWN:
                    new_bank = max(self.__bank - 1, 0)
                else:
                    assert False, u'unknown Display midi message'
            if not self.__bank == new_bank:
                self.__show_bank = True
                if not self.__assigned_device_is_locked:
                    self.__bank = new_bank
                    self.__reassign_strips()
                else:
                    self.__assigned_device.store_chosen_bank(
                        self.__parent.instance_identifier(), new_bank)

    def __handle_device_page_up_down_ccs(self, cc_no, cc_value):
        if cc_value == CC_VAL_BUTTON_PRESSED and self.__assigned_device:
            assigned_device_parent_type = type(
                self.__assigned_device.canonical_parent).__name__
            if assigned_device_parent_type == 'Chain' or assigned_device_parent_type == 'DrumChain':
                rack_device = self.__assigned_device.canonical_parent.canonical_parent
                assigned_device_index = str(self.__assigned_device_index)
                if rack_device.chains and len(rack_device.chains) > 1:
                    selected_chain = rack_device.view.selected_chain
                    selected_chain_index = list(
                        rack_device.chains).index(selected_chain)
                    if cc_no == MX_DISPLAY_PAGE_DOWN:
                        if selected_chain_index > 0:
                            new_index = selected_chain_index - 1
                            if assigned_device_parent_type == 'Chain' and rack_device.class_name != 'MidiEffectGroupDevice':
                                for chain in rack_device.chains: 
                                    chain.devices[0].parameters[0].value = chain.devices[0].parameters[0].min
                                    chain.solo = False
                                rack_device.chains[new_index].devices[0].parameters[0].value = chain.devices[0].parameters[0].max
                                rack_device.chains[new_index].solo = True
                            self.song().view.select_device(
                                rack_device.chains[new_index].devices[0], True)
                            self.__reassign_strips()
                            self.__selected_track.set_data(
                                assigned_device_index, new_index)
                            if not self.__transport_locked:
                                self.send_midi((self.cc_status_byte(
                                ), FX_UPPER_BUTTON_ROW_BASE_CC + (selected_chain_index - 1), 1))
                    elif cc_no == MX_DISPLAY_PAGE_UP:
                        if selected_chain_index < len(rack_device.chains) - 1:
                            new_index = selected_chain_index + 1
                            if assigned_device_parent_type == 'Chain' and rack_device.class_name != 'MidiEffectGroupDevice':
                                for chain in rack_device.chains:
                                    chain.devices[0].parameters[0].value = chain.devices[0].parameters[0].min
                                    chain.solo = False
                                rack_device.chains[new_index].devices[0].parameters[0].value = chain.devices[0].parameters[0].max
                                rack_device.chains[new_index].solo = True
                            self.song().view.select_device(
                                rack_device.chains[new_index].devices[0], True)
                            self.__reassign_strips()
                            self.__selected_track.set_data(
                                assigned_device_index, new_index)
                            if not self.__transport_locked:
                                self.send_midi((self.cc_status_byte(
                                ), FX_UPPER_BUTTON_ROW_BASE_CC + (selected_chain_index + 1), 1))
                    else:
                        assert False, u'unknown Display midi message'

    def __handle_select_button_ccs(self, cc_no, cc_value):
        if cc_no == FX_SELECT_UPPER_BUTTON_ROW:
            if cc_value == CC_VAL_BUTTON_PRESSED:
                self.__parent.toggle_lock()
        elif cc_no == FX_SELECT_ENCODER_ROW:
            if cc_value == CC_VAL_BUTTON_PRESSED:
                new_index = min(len(self.song().scenes) - 1, max(
                    0, list(self.song().scenes).index(self.song().view.selected_scene) - 1))
                self.song().view.selected_scene = self.song().scenes[new_index]
        # elif cc_no == FX_SELECT_LOWER_BUTTON_ROW:
        #     if cc_value == CC_VAL_BUTTON_PRESSED:
        #         new_index = min(len(self.song().scenes) - 1, max(
        #             0, list(self.song().scenes).index(self.song().view.selected_scene) + 1))
        #         self.song().view.selected_scene = self.song().scenes[new_index]
        elif cc_no == FX_SELECT_POTIE_ROW:
            if cc_value == CC_VAL_BUTTON_PRESSED:
                self.song().view.selected_scene.fire_as_selected()
        elif cc_no == FX_SELECT_DRUM_PAD_ROW:
            if cc_value == CC_VAL_BUTTON_PRESSED:
                self.song().stop_all_clips()
        else:
            assert False, u'unknown select row midi message'

    def __handle_transport_ccs(self, cc_no, cc_value):
        if cc_no == TS_LOCK:
            self.__transport_locked = cc_value != CC_VAL_BUTTON_RELEASED
            self.__on_transport_lock_changed()
        else:
            assert False, u'unknown Transport CC ' + str(cc_no)

    def __on_transport_lock_changed(self):
        self.__reassign_strips()

    def __update_select_row_leds(self):
        if self.__assigned_device_is_locked:
            self.send_midi(
                (self.cc_status_byte(), FX_SELECT_UPPER_BUTTON_ROW, CC_VAL_BUTTON_PRESSED))
        else:
            self.send_midi(
                (self.cc_status_byte(), FX_SELECT_UPPER_BUTTON_ROW, CC_VAL_BUTTON_RELEASED))

    def lock_to_device(self, device):
        if device:
            self.__assigned_device_is_locked = True
            self.__change_assigned_device(device)
            self.__update_select_row_leds()
            self.__reassign_strips()

    def unlock_from_device(self, device):
        if device and device == self.__assigned_device:
            self.__assigned_device_is_locked = False
            self.__update_select_row_leds()
            if not self.__parent.song().appointed_device == self.__assigned_device:
                self.__reassign_strips()

    def set_appointed_device(self, device):
        if not self.__assigned_device_is_locked:
            self.__change_assigned_device(device)
            self.__update_select_row_leds()
            self.__reassign_strips()

    def __report_bank(self):
        if self.__show_bank:
            self.__show_bank = False
            if self.__assigned_device.class_name in list(DEVICE_DICT.keys()):
                if self.__assigned_device.class_name in list(BANK_NAME_DICT.keys()):
                    bank_names = BANK_NAME_DICT[self.__assigned_device.class_name]
                    if bank_names and len(bank_names) > self.__bank:
                        bank_name = bank_names[self.__bank]
                        self.__show_bank_select(bank_name)
                else:
                    self.__show_bank_select(u'Best of Parameters')
            else:
                self.__show_bank_select(u'Bank' + str(self.__bank + 1))

    def __show_bank_select(self, bank_name):
        if self.__assigned_device:
            self.__parent.show_message(
                str(self.__assigned_device.name + u' Bank: ' + bank_name))

    def restore_bank(self, bank):
        if self.__assigned_device_is_locked:
            self.__bank = bank
            self.__reassign_strips()

    def __change_assigned_device(self, device):
        if not device == self.__assigned_device:
            self.__bank = 0
            if not self.__assigned_device == None:
                self.__assigned_device.remove_parameters_listener(
                    self.__device_changed)
                self.__assigned_device.remove_is_active_listener(
                    self.__device_changed)
            self.__show_bank = False
            self.__assigned_device = device
            if not self.__assigned_device == None:
                self.__assigned_device.add_parameters_listener(
                    self.__device_changed)
                self.__assigned_device.add_is_active_listener(
                    self.__device_changed)

    def __device_changed(self):
        self.__reassign_strips()


class EffectChannelStrip(object):
    u"""Represents one of the 8 strips in the Effect controls that we use for parameter
    controlling (one button, one encoder)
    """

    def __init__(self, effect_controller_parent, index):
        self.__effect_controller = effect_controller_parent
        self.__index = index
        self.__assigned_parameter = None

    def assigned_parameter(self):
        return self.__assigned_parameter

    def set_assigned_parameter(self, parameter):
        self.__assigned_parameter = parameter

    def on_upper_button_pressed(self):
        selected_track = self.__effect_controller.remote_sl_selected_track()

        assigned_device = self.__effect_controller.remote_sl_assigned_device()
        assigned_device_index = self.__effect_controller.remote_sl_assigned_device_index()

        assigned_device_type = type(assigned_device).__name__
        assigned_device_parent_type = type(
            assigned_device.canonical_parent).__name__

        if self.__effect_controller.remote_sl_transport_locked():
            assigned_device_chain_n = None

            if FX_LOWER_BUTTON_ROW_DEVICE_CHILDS and (assigned_device_parent_type == 'Chain' or assigned_device_parent_type == 'DrumChain'):
                rack_device = assigned_device.canonical_parent.canonical_parent
                for n, chain in enumerate(rack_device.chains):
                    if chain == assigned_device.canonical_parent:
                        # Make a string, otherwise None = 0
                        assigned_device_chain_n = str(n)

            if assigned_device_chain_n:
                snapshot_key = f'{str(assigned_device_index)}_{assigned_device_chain_n}_{str(self.__index)}'
            else:
                snapshot_key = f'{str(assigned_device_index)}_{str(self.__index)}'

            snapshot_data = selected_track.get_data(snapshot_key, None)

            if self.__index < self.__effect_controller.remote_sl_count():
                # LOAD
                parameter_values = snapshot_data
                for parameter, parameter_value in zip(assigned_device.parameters, parameter_values):
                    parameter.value = parameter_value
                self.__effect_controller.remote_sl_reassign_strips()

            elif self.__index == self.__effect_controller.remote_sl_count():
                if not snapshot_data:
                    # SAVE
                    selected_track.set_data(
                        snapshot_key, [parameter.value for parameter in assigned_device.parameters])
                else:
                    # LOAD
                    parameter_values = snapshot_data
                    for parameter, parameter_value in zip(assigned_device.parameters, parameter_values):
                        parameter.value = parameter_value
                self.__effect_controller.remote_sl_reassign_strips()
        else:
            if self.__assigned_parameter and self.__assigned_parameter.is_enabled:
                if self.__assigned_parameter.is_quantized:
                    if self.__assigned_parameter.value + 1 > self.__assigned_parameter.max:
                        self.__assigned_parameter.value = self.__assigned_parameter.min
                    else:
                        self.__assigned_parameter.value = self.__assigned_parameter.value + 1
                else:
                    self.__assigned_parameter.value = self.__assigned_parameter.default_value

    def on_lower_button_pressed(self):
        selected_track = self.__effect_controller.remote_sl_selected_track()
        if selected_track:
            if self.__index < len(selected_track.devices):
                self.__effect_controller.remote_sl_parent().send_midi(
                    (self.__effect_controller.cc_status_byte(), self.__index + FX_LOWER_BUTTON_ROW_BASE_CC, 1))
                device = selected_track.devices[self.__index]
                assigned_device_type = type(device).__name__
                if assigned_device_type == 'RackDevice' and FX_LOWER_BUTTON_ROW_DEVICE_CHILDS:
                    threshold = 1
                    if device.class_name == 'MidiEffectGroupDevice':
                        threshold = 0
                    if device.chains and len(device.chains) > threshold:
                        last_chain_key = str(self.__index)
                        last_chain_n = selected_track.get_data(
                            last_chain_key, 0)
                        device = device.chains[last_chain_n].devices[0]
                    self.__effect_controller.remote_sl_parent().song().view.select_device(device, True)
                else:
                    # self.__effect_controller.set_appointed_device(device)
                    self.__effect_controller.remote_sl_parent().song().view.select_device(device, True)

    def on_encoder_moved(self, cc_value):
        assert self.__assigned_parameter == None, u'should only be reached when the encoder was not realtime mapped '
