"""Classic evasi0n-style GTK window with live, read-only device information."""
import json
import threading
import time
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk
from .device import PROJECT, probe
from .flow import Limera1nFlow, compatible, ecid_number
from .pipeline import IOS511Pipeline, firmware_supported

CSS = b'''
window.classic { background: #202020; color: #f2f2f2; }
.classic label { font-family: "SF Pro Text", ".AppleSystemUIFont", "Helvetica Neue", sans-serif; font-size: 12px; color: #ededed; }
.classic button { min-height: 26px; min-width: 88px; padding: 0 12px; border-radius: 7px; border: 1px solid #515151; background: linear-gradient(#444, #393939); color: #f7f7f7; box-shadow: inset 0 1px alpha(#fff,.06); font-size: 12px; }
.classic button:hover { background: #4a4a4a; }
.classic button:active { background: #323232; }
.classic button:disabled { color: #858585; border-color: #414141; background: #303030; box-shadow: none; }
.classic button.primary { background: #0a84ff; border-color: #389bff; font-weight: 600; }
.classic button.primary:hover { background: #2994ff; }
.classic button.primary:active { background: #0067d4; }
.classic button.primary:disabled { background: #303030; border-color: #414141; color: #858585; }
.classic button:focus-visible { outline: 2px solid #70b5ff; outline-offset: 3px; }
.classic progressbar trough { min-height: 6px; border: 1px solid #484848; border-radius: 5px; background: #151515; box-shadow: none; }
.classic progressbar progress { min-width: 0; min-height: 6px; border-radius: 5px; background: #0a84ff; border: 0; }
.classic separator { min-height: 1px; background: #414141; box-shadow: none; }
.classic .brand-title { font-size: 26px; font-weight: 700; letter-spacing: -0.7px; color: #fafafa; }
.classic .beta { font-size: 10px; font-weight: 600; color: #b8b8b8; border: 1px solid #4a4a4a; border-radius: 4px; padding: 2px 5px; }
.classic .subtitle { color: #a6a6a6; font-size: 12px; }
.classic .device-status { color: #c7c7c7; }
.classic .team { background: #292929; border: 1px solid #3b3b3b; border-radius: 10px; padding: 15px; }
.classic .team-title { color: #ededed; font-weight: 600; font-size: 13px; }
.classic .team-copy { color: #b5b5b5; font-size: 12px; }
.classic .footer { font-size: 10px; color: #939393; }
.classic .link { color: #79b8ff; font-size: 11px; }
.classic textview, .classic textview text, .classic scrolledwindow { background: #1c1c1c; color: #ededed; }
.classic textview text selection { background: #264f78; color: #fff; }
.classic scrollbar { background: #202020; }
.classic scrollbar slider { background: #5a5a5a; }
.classic .details-title { font-size: 15px; font-weight: bold; }
.classic .value { font-family: monospace; font-size: 11px; }
'''


def text(value='', css=None, wrap=False):
    obj = Gtk.Label(label=value, xalign=0)
    obj.set_wrap(wrap)
    if css:
        obj.add_css_class(css)
    return obj


class RemedWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='remed1st beta')
        self.set_default_size(540, 400)
        self.set_resizable(False)
        self.add_css_class('classic')
        self.closed = False
        self.wake = threading.Event()
        self.device_lock = threading.Lock()
        self.last_state = None
        self.busy = False
        self.flow = None
        self.pulsing = False
        self.result_until = 0
        self.result_ecid = None
        self.details = None
        self.detail_labels = {}
        self.activity = []
        self.activity_window = None
        self.activity_buffer = None
        self.connect('close-request', self.on_close)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for edge in ('top', 'bottom', 'start', 'end'):
            getattr(body, 'set_margin_' + edge)(22)
        self.set_child(body)
        brand = Gtk.Box(spacing=16)
        mark = Gtk.Picture.new_for_filename(str(PROJECT / 'assets/remed-mark.svg'))
        mark.set_size_request(72, 72)
        mark.set_valign(Gtk.Align.CENTER)
        brand.append(mark)
        identity = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        identity.set_valign(Gtk.Align.CENTER)
        title_row = Gtk.Box(spacing=9)
        self.welcome = text('remed1st', 'brand-title')
        title_row.append(self.welcome)
        beta = text('BETA', 'beta')
        beta.set_valign(Gtk.Align.CENTER)
        title_row.append(beta)
        identity.append(title_row)
        identity.append(text('iPhone 4  ·  iOS 5.1.1', 'subtitle'))
        brand.append(identity)
        body.append(brand)
        self.status = text('Waiting for a connected iPhone.', 'device-status', wrap=True)
        self.status.set_size_request(-1, 43)
        self.status.set_valign(Gtk.Align.CENTER)
        self.status.set_margin_top(17)
        body.append(self.status)
        controls = Gtk.Box(spacing=16)
        controls.set_margin_top(5)
        self.progress = Gtk.ProgressBar()
        self.progress.set_hexpand(True)
        self.progress.set_valign(Gtk.Align.CENTER)
        self.progress.set_size_request(0, -1)
        controls.append(self.progress)
        self.info_button = Gtk.Button(label='Jailbreak')
        self.info_button.add_css_class('primary')
        self.info_button.set_valign(Gtk.Align.CENTER)
        self.info_button.set_sensitive(False)
        self.info_button.connect('clicked', self.begin_flow)
        controls.append(self.info_button)
        body.append(controls)
        team = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        team.add_css_class('team')
        team.set_margin_top(23)
        team.append(text('remed1st team', 'team-title'))
        team.append(text('@aliyabuz25', 'team-copy', wrap=True))
        body.append(team)
        self.limera1n = text('With thanks to @geohot.', 'footer')
        self.limera1n.set_margin_top(15)
        body.append(self.limera1n)
        footer = Gtk.Box()
        footer.set_margin_top(16)
        archive_link = self.link('Activity log', self.open_activity)
        archive_link.set_hexpand(True)
        archive_link.set_halign(Gtk.Align.START)
        footer.append(archive_link)
        footer.append(self.link('Device information', self.open_details))
        body.append(footer)
        threading.Thread(target=self.monitor, daemon=True).start()

    def link(self, title, action):
        obj = text(title, 'link')
        obj.set_cursor_from_name('pointer')
        gesture = Gtk.GestureClick()
        gesture.connect('released', lambda *_: action())
        obj.add_controller(gesture)
        return obj

    def monitor(self):
        while not self.closed:
            if self.busy:
                self.wake.wait(0.5)
                self.wake.clear()
                continue
            with self.device_lock:
                if self.busy or self.closed:
                    continue
                state = probe()
            if not self.closed:
                GLib.idle_add(self.render, state)
            self.wake.wait(3)
            self.wake.clear()

    def render(self, state):
        if self.closed or self.busy:
            return GLib.SOURCE_REMOVE
        self.last_state = state
        # Automatically exit recovery mode so the device returns to normal.
        if state.connected and state.mode in ('Recovery', 'DFU') and state.tools.get('irecovery'):
            def exit_recovery():
                import subprocess
                try:
                    subprocess.run([state.tools['irecovery'], '-n'],
                                   capture_output=True, timeout=5)
                except Exception:
                    pass
            threading.Thread(target=exit_recovery, daemon=True).start()
        if self.result_ecid is not None:
            try:
                changed = ecid_number(self.result_ecid) != ecid_number(state.ecid)
            except ValueError:
                changed = True
            if changed:
                self.result_until = 0
                self.result_ecid = None
        self.info_button.set_label('Jailbreak')
        ready = compatible(state) and firmware_supported(state)
        self.info_button.set_sensitive(ready and not self.get_application().smoke_seconds)
        if time.monotonic() >= self.result_until:
            if ready:
                version = f'iOS {state.version}' if state.mode == 'Normal' else state.mode
                self.status.set_text(f'{state.model} · {version}\nReady for jailbreak.')
            elif state.connected:
                self.status.set_text(f'{state.model} (iOS {state.version})\nThis workflow requires iPhone 4 GSM / iOS 5.1.1 (9B208).')
            else:
                self.status.set_text(state.message)
        for key, widget in self.detail_labels.items():
            widget.set_text(str(getattr(state, key)))
        if self.details:
            self.details.set_title(f'{state.model} – Device information')
        return GLib.SOURCE_REMOVE

    def begin_flow(self, *_):
        if self.get_application().smoke_seconds:
            return
        if self.busy:
            if self.flow:
                self.flow.cancel()
                self.info_button.set_sensitive(False)
            return
        if not self.last_state or not compatible(self.last_state) or not firmware_supported(self.last_state):
            return
        self.busy = True
        self.result_until = 0
        self.progress.set_fraction(0)
        self.info_button.set_label('Cancel')
        pipeline = IOS511Pipeline()
        self.flow = Limera1nFlow(lambda message, fraction: GLib.idle_add(self.flow_update, message, fraction),
                                preflight=pipeline.preflight, after_pwn=pipeline)
        target, flow = self.last_state, self.flow
        def work():
            with self.device_lock:
                success = flow.run(target)
            GLib.idle_add(self.flow_done, success)
        GLib.timeout_add(120, self.pulse)
        threading.Thread(target=work, daemon=True).start()

    def pulse(self):
        if self.closed or not self.busy:
            return GLib.SOURCE_REMOVE
        if self.pulsing:
            self.progress.pulse()
        return GLib.SOURCE_CONTINUE

    def flow_update(self, message, fraction):
        if self.closed:
            return GLib.SOURCE_REMOVE
        self.status.set_text(message)
        if not self.activity or self.activity[-1] != message:
            self.activity.append(message)
            self.activity = self.activity[-300:]
            if self.activity_buffer:
                self.activity_buffer.set_text('\n\n'.join(self.activity))
        self.pulsing = fraction is None
        if fraction is not None:
            self.progress.set_fraction(fraction)
        return GLib.SOURCE_REMOVE

    def flow_done(self, success):
        if self.closed:
            return GLib.SOURCE_REMOVE
        self.busy = False
        self.pulsing = False
        self.flow = None
        self.result_until = float('inf')
        self.result_ecid = self.last_state.ecid
        self.info_button.set_label('Jailbreak')
        self.info_button.set_sensitive(False)
        self.wake.set()
        return GLib.SOURCE_REMOVE

    def open_details(self, *_):
        if self.details:
            self.details.present()
            return
        self.details = Gtk.Window(title='Device information', transient_for=self, modal=True)
        self.details.add_css_class('classic')
        self.details.set_default_size(490, 440)
        self.details.connect('close-request', self.close_details)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for edge in ('top', 'bottom', 'start', 'end'):
            getattr(body, 'set_margin_' + edge)(18)
        self.details.set_child(body)
        body.append(text('Connected device', 'details-title'))
        grid = Gtk.Grid(column_spacing=16, row_spacing=8)
        body.append(grid)
        for index, (key, title) in enumerate([
            ('name', 'Device name'), ('model', 'Model'), ('product', 'Product type'),
            ('version', 'iOS version'), ('build', 'Build'), ('mode', 'Mode'),
            ('serial', 'Serial number'), ('ecid', 'ECID'), ('udid', 'UDID'),
            ('activation', 'Activation')]):
            grid.attach(text(title), 0, index, 1, 1)
            value = text(str(getattr(self.last_state, key)) if self.last_state else '—', 'value', True)
            value.set_selectable(True)
            value.set_hexpand(True)
            grid.attach(value, 1, index, 1, 1)
            self.detail_labels[key] = value
        button = Gtk.Button(label='Copy information')
        button.set_halign(Gtk.Align.END)
        button.connect('clicked', self.copy_info)
        body.append(button)
        self.details.present()

    def close_details(self, *_):
        self.detail_labels.clear()
        self.details = None
        return False

    def copy_info(self, *_):
        if self.last_state:
            self.get_clipboard().set(json.dumps(self.last_state.to_dict(), ensure_ascii=False, indent=2))

    def open_downloads(self, *_):
        Gio.AppInfo.launch_default_for_uri((PROJECT / 'downloads').as_uri(), None)

    def open_activity(self, *_):
        if self.activity_window:
            self.activity_window.present()
            return
        self.activity_window = Gtk.Window(title='Activity log', transient_for=self)
        self.activity_window.add_css_class('classic')
        self.activity_window.set_default_size(560, 400)
        scroll = Gtk.ScrolledWindow()
        view = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        view.set_top_margin(16)
        view.set_left_margin(16)
        view.set_right_margin(16)
        self.activity_buffer = view.get_buffer()
        self.activity_buffer.set_text('\n\n'.join(self.activity) or 'No activity yet.')
        scroll.set_child(view)
        self.activity_window.set_child(scroll)
        self.activity_window.connect('close-request', self.close_activity)
        self.activity_window.present()

    def close_activity(self, *_):
        self.activity_window = None
        self.activity_buffer = None
        return False

    def on_close(self, *_):
        self.closed = True
        if self.flow:
            self.flow.cancel()
        self.wake.set()
        if self.details:
            self.details.close()
        if self.activity_window:
            self.activity_window.close()
        return False


class RemedApp(Gtk.Application):
    def __init__(self, smoke_seconds=0):
        super().__init__(application_id='io.remed1st.DeviceMonitor', flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.smoke_seconds = smoke_seconds
        self.smoke_passed = False

    def do_activate(self):
        settings = Gtk.Settings.get_default()
        if settings.find_property('gtk-interface-color-scheme'):
            settings.set_property('gtk-interface-color-scheme', Gtk.InterfaceColorScheme.DARK)
        else:
            settings.set_property('gtk-application-prefer-dark-theme', True)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.window = RemedWindow(self)
        # Set app icon from remed-mark.svg
        try:
            icon_path = str(PROJECT / 'assets/remed-mark.svg')
            icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
            icon_theme.add_search_path(str(PROJECT / 'assets'))
            texture = Gdk.Texture.new_from_filename(icon_path)
            self.window.set_icon_name('')
            paintable = Gtk.IconPaintable.new_for_file(Gio.File.new_for_path(icon_path), 96, 1)
            self.window.set_default_icon_name('remed-mark')
        except Exception:
            pass
        self.window.present()
        if self.smoke_seconds:
            GLib.timeout_add_seconds(self.smoke_seconds, self.finish_smoke)

    def finish_smoke(self):
        self.smoke_passed = self.window.last_state is not None
        if self.smoke_passed:
            state = self.window.last_state
            print(f'GTK verified: connected={state.connected}, model={state.product}, iOS={state.version}', flush=True)
        else:
            print('GTK monitor did not return a state', flush=True)
        if self.smoke_passed:
            try:
                body = self.window
                paintable = Gtk.WidgetPaintable.new(body)
                snapshot = Gtk.Snapshot.new()
                paintable.snapshot(snapshot, body.get_width(), body.get_height())
                node = snapshot.to_node()
                texture = self.window.get_renderer().render_texture(node, None)
                texture.save_to_png(str(PROJECT / 'design/preview.png'))
            except Exception as error:
                print(f'Optional preview capture: {error}', flush=True)
        self.window.close()
        self.quit()
        return GLib.SOURCE_REMOVE
