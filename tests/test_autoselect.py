import importlib
import logging
import sys
import types
import unittest


class PluginMixin:
	pass


class FileDestinations:
	LOCAL = "local"
	PRINTER = "printer"
	SDCARD = "sdcard"


class FakeTimer:
	instances = []

	def __init__(self, interval, function):
		self.interval = interval
		self.function = function
		self.cancelled = False
		self.daemon = False
		self.started = False
		self.instances.append(self)

	def cancel(self):
		self.cancelled = True

	def start(self):
		self.started = True

	def fire(self):
		if not self.cancelled:
			self.function()


class Settings:
	def __init__(self, delay=5):
		self.delay = delay

	def get_float(self, path):
		return self.delay


class FileManager:
	def __init__(self):
		self.created_jobs = []

	def create_job(self, storage, path):
		job = types.SimpleNamespace(storage=storage, path=path)
		self.created_jobs.append(job)
		return job

	def path_on_disk(self, storage, path):
		return "/uploads/{}".format(path)


class Printer:
	def __init__(self):
		self.ready = True
		self.current_job = None
		self.selected = []
		self.jobs = []

	def is_ready(self):
		return self.ready

	def is_current_file(self, path, is_printer_storage):
		return bool(
			self.current_job
			and self.current_job.path == path
			and self.current_job.storage
			== (
				FileDestinations.SDCARD
				if is_printer_storage
				else FileDestinations.LOCAL
			)
		)

	def select_file(self, path, is_printer_storage, printAfterSelect=False):
		self.selected.append((path, is_printer_storage, printAfterSelect))

	def set_job(self, job, print_after_select=False):
		self.jobs.append((job, print_after_select))


def load_plugin():
	octoprint = types.ModuleType("octoprint")
	plugin = types.ModuleType("octoprint.plugin")
	for mixin in (
		"EventHandlerPlugin",
		"SettingsPlugin",
		"ShutdownPlugin",
		"TemplatePlugin",
	):
		setattr(plugin, mixin, type(mixin, (PluginMixin,), {}))
	plugin.SettingsPlugin.on_settings_save = lambda self, data: None

	events = types.ModuleType("octoprint.events")
	events.Events = types.SimpleNamespace(FILE_ADDED="FileAdded")

	filemanager = types.ModuleType("octoprint.filemanager")
	filemanager.FileDestinations = FileDestinations
	filemanager.valid_file_type = lambda path, type=None: path.endswith(
		(".gcode", ".gco")
	)

	version = types.ModuleType("octoprint.util.version")
	version.is_octoprint_compatible = lambda spec: False
	util = types.ModuleType("octoprint.util")
	util.version = version

	octoprint.plugin = plugin
	octoprint.events = events
	octoprint.filemanager = filemanager
	octoprint.util = util

	modules = {
		"octoprint": octoprint,
		"octoprint.plugin": plugin,
		"octoprint.events": events,
		"octoprint.filemanager": filemanager,
		"octoprint.util": util,
		"octoprint.util.version": version,
	}
	for name, module in modules.items():
		sys.modules[name] = module

	sys.modules.pop("octoprint_autoselect", None)
	return importlib.import_module("octoprint_autoselect")


class AutoselectTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.module = load_plugin()

	def setUp(self):
		FakeTimer.instances = []
		self.module.threading.Timer = FakeTimer
		self.module.is_octoprint_compatible = lambda spec: False

		self.plugin = self.module.AutoselectPlugin()
		self.plugin._settings = Settings()
		self.plugin._file_manager = FileManager()
		self.plugin._printer = Printer()
		self.plugin._logger = logging.getLogger("test_autoselect")

	def add_file(self, path="part.gcode", storage=FileDestinations.LOCAL):
		self.plugin.on_event(
			self.module.Events.FILE_ADDED,
			{"storage": storage, "path": path},
		)

	def test_selects_local_file_after_delay_on_octoprint_1(self):
		self.add_file()

		timer = FakeTimer.instances[-1]
		self.assertEqual(timer.interval, 5)
		self.assertTrue(timer.started)
		timer.fire()

		self.assertEqual(
			self.plugin._printer.selected,
			[("/uploads/part.gcode", False, False)],
		)

	def test_uses_job_api_on_octoprint_2(self):
		self.module.is_octoprint_compatible = lambda spec: True
		self.add_file(storage=FileDestinations.PRINTER)

		FakeTimer.instances[-1].fire()

		job, print_after_select = self.plugin._printer.jobs[0]
		self.assertEqual((job.storage, job.path), ("printer", "part.gcode"))
		self.assertFalse(print_after_select)

	def test_does_not_replace_explicit_selection_on_octoprint_2(self):
		self.module.is_octoprint_compatible = lambda spec: True
		self.plugin._printer.current_job = types.SimpleNamespace(
			storage=FileDestinations.LOCAL, path="part.gcode"
		)
		self.add_file()

		FakeTimer.instances[-1].fire()

		self.assertEqual(self.plugin._printer.jobs, [])

	def test_does_not_replace_explicit_selection_on_octoprint_1(self):
		self.plugin._printer.current_job = types.SimpleNamespace(
			storage=FileDestinations.LOCAL, path="part.gcode"
		)
		self.add_file()

		FakeTimer.instances[-1].fire()

		self.assertEqual(self.plugin._printer.selected, [])

	def test_latest_added_file_wins(self):
		self.add_file("first.gcode")
		first_timer = FakeTimer.instances[-1]
		self.add_file("second.gcode")
		second_timer = FakeTimer.instances[-1]

		self.assertTrue(first_timer.cancelled)
		second_timer.fire()

		self.assertEqual(
			self.plugin._printer.selected,
			[("/uploads/second.gcode", False, False)],
		)

	def test_ignores_non_machinecode_files(self):
		self.add_file("notes.txt")

		self.assertEqual(FakeTimer.instances, [])

	def test_skips_selection_if_printer_is_not_ready(self):
		self.plugin._printer.ready = False
		self.add_file()

		FakeTimer.instances[-1].fire()

		self.assertEqual(self.plugin._printer.selected, [])


if __name__ == "__main__":
	unittest.main()
