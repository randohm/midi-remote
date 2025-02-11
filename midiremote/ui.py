import sys, os
import argparse
import logging
import signal
import yaml
import mido
import gi

gi.require_version("Gtk", "4.0")
#gi.require_version('Adw', '1')
from gi.repository import Gtk, Gdk, Gio #, Adw, GdkPixbuf, GObject, Pango, GLib

class Defaults:
    """
    Static class for default values and logger.
    """
    application_id = "com.github.randohm.midi-remote"
    window_title = "MIDI Remote"
    window_width = 500
    window_height = 100
    config_file = "./config.yml"
    css_file = "./style.css"
    log_format = "%(asctime)s %(levelname)s %(module)s::%(funcName)s(%(lineno)d): %(message)s"
    log = None
    min_widgets_per_row = 2

    @staticmethod
    def init_logger():
        """
        Create and initialize logger object
        :return: None
        """
        log = logging.getLogger(__name__)
        log.setLevel(logging.INFO)
        formatter = logging.Formatter(Defaults.log_format)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        log.addHandler(handler)
        Defaults.log = log

    @staticmethod
    def get_logger():
        """
        Returns the logging object
        :return: logging object
        """
        return Defaults.log

def signal_exit(sig, frame):
    """
    Perform a clean exit.
    """
    Defaults.get_logger().debug("caught signal %s, exiting" % signal.Signals(sig).name)
    sys.exit(0)

class RowOfGroups:
    def __init__(self, config=None, device=None):
        if not config or not device:
            raise ValueError("config or device  cannot be None")
        if not 'name' in config.keys():
            raise RuntimeError("'name' is not in config")
        self.name = config['name']
        self.device = device
        self.config = config
        self.groups = []
        if 'expand' in config.keys():
            self.expand = config['expand']
        else:
            self.expand = True
        if 'min' in config.keys():
            self.min = config['min']
        else:
            self.min = 2

class MidiCcControl:
    cc_num = 0
    default_value = 0

    def __init__(self, config=None, device=None):
        if not config or not device:
            raise ValueError("config or device  cannot be None")
        self.log = Defaults.get_logger()
        self.name = config['name']
        self.cc_num = int(config['cc'])
        self.control_type = config['type']
        self.values = config['values']
        if config['default']:
            self.default_value = int(config['default'])
        self.device = device

    def send_message(self, value=None):
        if not value is None:
            self.device.send_cc_message(self.cc_num, value)
        else:
            log.info("trying to send a None value for CC")

class MidiCCGroup:
    controls = None
    def __init__(self, config=None, device=None):
        if not config or not device:
            raise ValueError("config or device cannot be None")
        self.name = config['name']
        self.controls = []
        for cfg in config['controls']:
            ctrl = MidiCcControl(config=cfg, device=device)
            self.controls.append(ctrl)

class MidiDevice:
    def __init__(self, config=None, override_port=None):
        if not config:
            raise ValueError("config cannot be None")
        self.log = Defaults.get_logger()
        self.name = config['name']
        if override_port:
            self.port = override_port
        else:
            self.port = config['port']
        self.channel = int(config['channel'])
        try:
            self.midi_port = mido.open_output(self.port)
        except Exception as e:
            self.log.error("could not create midi port: %s. possible ports: %s" % (e, mido.get_output_names()))
            raise IOError(e)
        self.log.debug("midi device, name=%s channel=%d" % (self.name, self.channel))

        self.rows = []
        self.groups = []
        if not 'rows' in config.keys():
            raise RuntimeError("'rows' is not in config")
        for r in config['rows']:
            log.debug("creating row %s" % r['name'])
            row = RowOfGroups(config=r, device=self)
            if not 'groups' in r.keys():
                raise RuntimeError("'groups' is not in config")
            for g in r['groups']:
                log.debug("creating group %s" % g['name'])
                group = MidiCCGroup(config=g, device=self)
                row.groups.append(group)
                self.groups.append(group)
            self.rows.append(row)

    def send_pc_message(self, pc):
        log.debug("sending PC message: %s channel: %s port: %s" % (pc, self.channel, self.port))
        msg = mido.Message('program_change', channel=self.channel-1, program=pc)
        self.midi_port.send(msg)

    def send_cc_message(self, cc, value):
        log.debug("sending CC message cc:%s value: %s channel: %s port: %s" % (cc, value, self.channel, self.port))
        msg = mido.Message('control_change', channel=self.channel-1, control=cc, value=value)
        self.midi_port.send(msg)

class MidiRemote:
    def __init__(self, config=None, app=None, override_port=None):
        if not config:
            raise ValueError("config cannot be None")
        if not app:
            raise ValueError("window cannot be None")

        self.override_port = override_port
        self.log = Defaults.get_logger()
        self.config = config
        self.app = app
        self.devices = []
        self.load_devices()

    def load_devices(self):
        """
        Creates MIDI devices from config
        """
        for cfg in self.config['devices']:
            #self.log.debug("device cfg: %s" % cfg)
            try:
                device = MidiDevice(config=cfg, override_port=self.override_port)
                self.devices.append(device)
            except Exception as e:
                self.log.error("could not create MidiDevice: %s" % e)

class DeviceWidget(Gtk.Box):
    def __init__(self, device=None, *args, **kwargs):
        if not device:
            raise ValueError("control cannot be None")
        super().__init__(orientation=Gtk.Orientation.VERTICAL, *args, **kwargs)
        self.log = Defaults.get_logger()
        self.device = device
        self.set_hexpand(False)
        self.set_vexpand(False)

        self.device_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.device_box.set_spacing(8)
        self.device_name_label = Gtk.Label(label=device.name)
        self.device_channel_label = Gtk.Label(label="port: %s" % device.port)
        self.device_port_label = Gtk.Label(label="channel: %s" % device.channel)
        self.pc_send_b = Gtk.Button(label="PC")
        self.pc_spin_b = Gtk.SpinButton(adjustment=Gtk.Adjustment(value=0, step_increment=1, lower=0, upper=127))
        self.cc_send_b = Gtk.Button(label="CC")
        self.cc_spin_b = Gtk.SpinButton(adjustment=Gtk.Adjustment(value=0, step_increment=1, lower=0, upper=127))
        self.cc_value_label = Gtk.Label(label="CC Value")
        self.cc_value_spin_b = Gtk.SpinButton(adjustment=Gtk.Adjustment(value=0, step_increment=1, lower=0, upper=127))
        self.width_label = Gtk.Label(label="Min Width")
        self.width_spin_b = Gtk.SpinButton(adjustment=Gtk.Adjustment(value=Defaults.min_widgets_per_row, step_increment=1,
                                                                     lower=1, upper=20))

        self.pc_send_b.connect('clicked', self.on_pc_clicked)
        self.cc_send_b.connect('clicked', self.on_cc_clicked)
        self.width_spin_b.connect('value-changed', self.on_minwidth_changed)

        self.device_box.set_css_classes(['title_box'])
        self.device_name_label.set_css_classes(['title'])
        self.device_channel_label.set_css_classes(['title_info'])
        self.device_port_label.set_css_classes(['title_info'])

        self.device_box.append(self.device_name_label)
        self.device_box.append(self.device_channel_label)
        self.device_box.append(self.device_port_label)
        self.device_box.append(self.pc_send_b)
        self.device_box.append(self.pc_spin_b)
        self.device_box.append(self.cc_send_b)
        self.device_box.append(self.cc_spin_b)
        self.device_box.append(self.cc_value_label)
        self.device_box.append(self.cc_value_spin_b)
        self.device_box.append(self.width_label)
        self.device_box.append(self.width_spin_b)
        self.append(self.device_box)

        self.rows = []
        for r in device.rows:
            row = RowWidget(r)
            self.append(row)
            self.rows.append(row)

    def on_pc_clicked(self, button):
        self.device.send_pc_message(self.pc_spin_b.get_value_as_int())

    def on_cc_clicked(self, button):
        self.device.send_cc_message(self.cc_spin_b.get_value_as_int(), self.cc_value_spin_b.get_value_as_int())

    def on_minwidth_changed(self, button):
        for r in self.rows:
            v = button.get_value_as_int()
            r.box.set_min_children_per_line(v)

class RowWidget(Gtk.Expander):
    def __init__(self, row=None, *args, **kwargs):
        if not row:
            raise ValueError("row cannot be None")
        super().__init__(*args, **kwargs)
        self.row = row
        row_label = Gtk.Label(label=row.name)
        row_label.set_css_classes(['group_expander_label'])
        self.set_label_widget(label_widget=row_label)
        self.set_css_classes(['group_expander'])
        self.set_expanded(row.expand)
        self.set_resize_toplevel(True)
        self.set_hexpand(False)
        self.set_vexpand(False)

        #self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        #self.box.set_spacing(4)
        self.box = Gtk.FlowBox()
        self.box.set_css_classes(['row_of_groups_box'])
        self.box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.box.set_homogeneous(homogeneous=False)
        self.box.set_min_children_per_line(Defaults.min_widgets_per_row)
        #self.box.set_max_children_per_line(10)
        self.box.set_hexpand(False)
        self.box.set_vexpand(False)

        self.group_widgets = []
        for group in row.groups:
            group_w = CcGroupWidget(group=group)
            self.box.append(group_w)
            self.group_widgets.append(group_w)
        self.set_child(self.box)

class CcWidget(Gtk.Box):
    def __init__(self, control=None, *args, **kwargs):
        if not control:
            raise ValueError("control cannot be None")
        super().__init__(*args, **kwargs)
        self.log = Defaults.get_logger()
        self.control = control
        self.send_button = Gtk.Button(label=self.control.name)
        self.send_button.connect('clicked', self.on_button_clicked)
        self.send_button.set_css_classes(['send_button'])
        self.set_css_classes(['control_box'])

    def on_button_clicked(self, button):
        pass

    def get_value(self):
        pass

class CcBasicWidget(CcWidget):
    def __init__(self, control=None, *args, **kwargs):
        super().__init__(control=control, orientation=Gtk.Orientation.VERTICAL, *args, **kwargs)
        adjustment = Gtk.Adjustment(value=0, step_increment=1, lower=0, upper=127)
        self.spin_b = Gtk.SpinButton(adjustment=adjustment)
        self.append(self.spin_b)

class CcEnumWidget(CcWidget):
    def __init__(self, control=None, *args, **kwargs):
        super().__init__(control=control, orientation=Gtk.Orientation.VERTICAL, *args, **kwargs)
        self.append(self.send_button)
        self.send_button.set_css_classes(['send_button_enum'])

        group_button = None     ## normally assigned to the 1st button
        for k, v in control.values.items():
            radio_b = Gtk.CheckButton(label=k)
            radio_b.set_css_classes(['enum_radio'])
            if not group_button:
                group_button = radio_b
            else:
                radio_b.set_group(group_button)
            if self.control.default_value == v:
                radio_b.set_active(True)
                self.current_selection = v
            radio_b.connect('toggled', self.on_radio_toggled, v)
            self.append(radio_b)

    def on_radio_toggled(self, radio, name):
        if radio.props.active:
            self.current_selection = name
            self.control.send_message(int(name))

    def on_button_clicked(self, button):
        self.control.send_message(int(self.current_selection))

    def get_value(self):
        return self.current_selection

class CcToggleWidget(CcWidget):
    def __init__(self, control=None, *args, **kwargs):
        super().__init__(control=control, orientation=Gtk.Orientation.VERTICAL, *args, **kwargs)
        self.send_button.set_css_classes(['send_button_toggle'])
        box = Gtk.Box()
        box.set_css_classes(['toggle_box'])
        self.switch = Gtk.Switch()
        if self.control.default_value:
            self.switch.set_active(self.control.default_value > 0)
        self.switch.connect('notify::active', self.on_switch_activated)
        box.append(self.switch)
        self.append(box)
        self.append(self.send_button)

    def on_switch_activated(self, switch, _gparam):
        if switch.props.active:
            self.control.send_message(value=self.control.values[True])
        else:
            self.control.send_message(value=self.control.values[False])

    def on_button_clicked(self, button):
        if self.switch.props.active:
            self.control.send_message(value=self.control.values[True])
        else:
            self.control.send_message(value=self.control.values[False])

    def get_value(self):
        if self.switch.props.active:
            return self.control.values[True]
        else:
            return self.control.values[False]

class CcContinuousWidget(CcWidget):
    def __init__(self, control=None, *args, **kwargs):
        super().__init__(control=control, orientation=Gtk.Orientation.VERTICAL, *args, **kwargs)
        self.send_button.set_css_classes(['send_button_cont'])
        adjustment = Gtk.Adjustment(value=int(control.default_value), step_increment=1,
                                    lower=int(control.values['min']), upper=int(control.values['max']))
        self.scale = Gtk.Scale(orientation=Gtk.Orientation.VERTICAL, adjustment=adjustment)
        self.scale.set_digits(0)
        self.scale.set_inverted(True)
        self.scale.set_draw_value(True)
        self.scale.set_has_origin(True)
        mid_point = round((control.values['max']-control.values['min'])/2)
        self.scale.add_mark(value=mid_point, position=Gtk.PositionType.LEFT, markup="%s" % mid_point)
        self.scale.add_mark(value=control.values['max'], position=Gtk.PositionType.LEFT, markup="%s" % control.values['max'])
        self.scale.add_mark(value=control.values['min'], position=Gtk.PositionType.LEFT, markup="%s" % control.values['min'])
        #self.scale.set_css_classes(['cont_scale'])
        self.scale.connect('value-changed', self.on_scale_changed)
        self.append(self.scale)
        self.append(self.send_button)

    def on_scale_changed(self, scale):
        self.control.send_message(int(scale.get_value()))

    def on_button_clicked(self, button):
        self.control.send_message(int(self.scale.get_value()))

    def get_value(self):
        return self.scale.get_value()

class CcWidgetFactory:
    @staticmethod
    def create_control_widget(control=None):
        if not control:
            raise ValueError("control cannot be None")
        if control.control_type == "enum":
            return CcEnumWidget(control=control)
        elif control.control_type == "toggle":
            return CcToggleWidget(control=control)
        elif control.control_type == "continuous":
            return CcContinuousWidget(control=control)
        return None

class CcGroupWidget(Gtk.Box):
    def __init__(self, group=None, *args, **kwargs):
        if not group:
            raise ValueError("group cannot be None")
        super().__init__(orientation=Gtk.Orientation.VERTICAL, *args, **kwargs)
        self.log = Defaults.get_logger()
        self.group = group
        self.set_hexpand(False)
        self.set_vexpand(False)
        self.set_css_classes(['group_box'])
        self.send_button = Gtk.Button.new_with_label(label=group.name)
        self.send_button.connect('clicked', self.on_label_button_clicked)
        self.send_button.set_css_classes(['group_label_button'])
        self.append(self.send_button)
        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.box.set_hexpand(False)
        self.box.set_vexpand(True)
        self.control_boxes = []
        for control in group.controls:
            control_box = CcWidgetFactory.create_control_widget(control=control)
            control_box.set_css_classes(['control_box'])
            control_box.set_hexpand(False)
            control_box.set_vexpand(True)
            self.box.append(control_box)
            self.control_boxes.append(control_box)
        self.append(self.box)

    def on_label_button_clicked(self, button):
        for c in self.control_boxes:
            c.control.send_message(int(c.get_value()))

class MidiRemoteWindow(Gtk.ApplicationWindow):
    def __init__(self, config=None, width=None, height=None, *args, **kwargs):
        if not config:
            raise ValueError("config cannot be None")
        super().__init__(*args, **kwargs)
        self.log = Defaults.get_logger()
        self.config = config
        self.controller = Gtk.EventControllerKey.new()
        self.controller.connect('key-pressed', self.on_keypress)
        self.add_controller(self.controller)

        self.set_title(Defaults.window_title)
        if not width:
            width = Defaults.window_width
        if not height:
            height = Defaults.window_height
        self.set_default_size(width, height)
        self.set_resizable(False)
        #self.set_show_menubar(True)
        self.set_decorated(True)
        self.layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.layout.set_css_classes(['main_layout'])
        self.set_child(self.layout)

    def display_devices(self, devices):
        for device in devices:
            device_box = DeviceWidget(device=device)
            self.layout.append(device_box)

    def on_keypress(self, controller, keyval, keycode, state):
        #self.log.debug("keypressed: %s %s %s" % (keyval, keycode, state))
        ctrl_pressed = state & Gdk.ModifierType.CONTROL_MASK
        cmd_pressed = state & Gdk.ModifierType.META_MASK
        if keyval in (ord('q'), ord('Q')) and (ctrl_pressed or cmd_pressed):
            self.log.debug("QUIT pressed")
            self.close()

class MidiRemoteApp(Gtk.Application):
    def __init__(self, config_path=None, css_file=None, override_port=None, *args, **kwargs):
        if not config_path:
            raise ValueError("config_path cannot be None")
        super().__init__(*args, **kwargs)
        self.log = Defaults.get_logger()

        try:
            with open(config_path, 'r') as config_file:
                self.config = yaml.load(config_file, Loader=yaml.SafeLoader)
        except Exception as e:
            err_msg = "Could not load config file %s: %s" % (config_file, e)
            self.log.critical(err_msg)
            raise e
        self.log.debug("loaded config: %s" % self.config)
        self.css_file = css_file

        self.connect('activate', self.on_activate)
        self.connect('shutdown', self.on_quit)

        if self.css_file and os.path.isfile(self.css_file):
            self.log.debug("reading css file: %s" % self.css_file)
            self.css_provider = Gtk.CssProvider.new()
            try:
                self.css_provider.load_from_path(self.css_file)
            except Exception as e:
                self.log.error("could not load CSS: %s" % e)
                self.css_provider = None

        try:
            self.remote = MidiRemote(config=self.config, app=self, override_port=override_port)
        except Exception as e:
            self.log.critical("could not create controller: %s" % e)
            raise e

    def on_activate(self, app):
        self.window = MidiRemoteWindow(application=self, config=self.config)
        self.window.display_devices(self.remote.devices)
        if self.css_provider:
            display = Gtk.Widget.get_display(self.window)
            Gtk.StyleContext.add_provider_for_display(display, self.css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.window.present()

    def on_quit(self, app):
        self.quit()

def print_output_ports():
    print("Available MIDI ports:")
    for p in mido.get_output_names():
        print(p)

if __name__ == "__main__":
    ## set signal handlers
    signal.signal(signal.SIGINT, signal_exit)
    signal.signal(signal.SIGTERM, signal_exit)

    ## parse args
    arg_parser = argparse.ArgumentParser(description="MPD Frontend", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    arg_parser.add_argument("-v", "--verbose", action='store_true', help="Turn on verbose output")
    arg_parser.add_argument("-c", "--config", default=Defaults.config_file, action='store', help="Config file")
    arg_parser.add_argument("-s", "--css", default=Defaults.css_file, action='store', help="CSS file")
    arg_parser.add_argument("-p", "--port", action='store', help="MIDI port")
    arg_parser.add_argument("-l", "--list", action='store_true', help="List available output ports")
    args = arg_parser.parse_args()

    Defaults.init_logger()
    log = Defaults.get_logger()

    if args.verbose:
        log.setLevel(logging.DEBUG)

    if args.list:
        print_output_ports()
        sys.exit(0)

    if not os.path.isfile(args.config):
        log.critical("config file not found %s" % args.config)
        sys.exit(1)

    try:
        app = MidiRemoteApp(config_path=args.config, css_file=args.css, application_id=Defaults.application_id, override_port=args.port)
    except Exception as e:
        log.critical("could not create application: %s" % e)
        sys.exit(3)

    app.run(None)
    sys.exit(0)
