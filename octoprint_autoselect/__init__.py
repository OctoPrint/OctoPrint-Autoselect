import threading

import octoprint.filemanager
import octoprint.plugin
from octoprint.events import Events
from octoprint.filemanager import FileDestinations
from octoprint.util.version import is_octoprint_compatible


class AutoselectPlugin(
	octoprint.plugin.EventHandlerPlugin,
	octoprint.plugin.SettingsPlugin,
	octoprint.plugin.ShutdownPlugin,
	octoprint.plugin.TemplatePlugin,
):
	def __init__(self):
		self._timer = None
		self._timer_lock = threading.Lock()

	def get_settings_defaults(self):
		return {"delay": 5}

	def on_settings_save(self, data):
		if "delay" in data:
			try:
				data["delay"] = max(0, float(data["delay"]))
			except (TypeError, ValueError):
				del data["delay"]

		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)

	def get_template_configs(self):
		return [{"type": "settings", "custom_bindings": False}]

	def is_template_autoescaped(self):
		return True

	def on_event(self, event, payload):
		if event != Events.FILE_ADDED:
			return

		storage = payload["storage"]
		path = payload["path"]
		if not octoprint.filemanager.valid_file_type(path, type="machinecode"):
			self._logger.debug("File is not a machinecode file, not autoselecting")
			return

		self._schedule_select(storage, path)

	def _schedule_select(self, storage, path):
		delay = max(0, self._settings.get_float(["delay"]))

		def select():
			with self._timer_lock:
				if self._timer is not timer:
					return
				self._timer = None
			self._select_file(storage, path)

		timer = threading.Timer(delay, select)
		timer.daemon = True

		with self._timer_lock:
			if self._timer is not None:
				self._timer.cancel()
			self._timer = timer
			timer.start()

	def _select_file(self, storage, path):
		if not self._printer.is_ready():
			self._logger.debug("Printer is not ready, not autoselecting added file")
			return

		if is_octoprint_compatible(">=2"):
			current_job = self._printer.current_job
			if (
				current_job is not None
				and current_job.storage == storage
				and current_job.path == path
			):
				return

			job = self._file_manager.create_job(storage, path)
			self._logger.info("Selecting %s on %s that was just added", path, storage)
			self._printer.set_job(job, print_after_select=False)
			return

		is_printer_storage = storage == FileDestinations.SDCARD
		if self._printer.is_current_file(path, is_printer_storage):
			return

		file_to_select = (
			path
			if is_printer_storage
			else self._file_manager.path_on_disk(storage, path)
		)
		self._logger.info("Selecting %s on %s that was just added", path, storage)
		self._printer.select_file(
			file_to_select, is_printer_storage, printAfterSelect=False
		)

	def on_shutdown(self):
		with self._timer_lock:
			if self._timer is not None:
				self._timer.cancel()
				self._timer = None

	def get_update_information(self):
		return {
			"autoselect": {
				"displayName": self._plugin_name,
				"displayVersion": self._plugin_version,
				"type": "github_release",
				"user": "OctoPrint",
				"repo": "OctoPrint-Autoselect",
				"current": self._plugin_version,
				"pip": (
					"https://github.com/OctoPrint/OctoPrint-Autoselect/"
					"archive/{target_version}.zip"
				),
			}
		}


__plugin_name__ = "Autoselect Plugin"
__plugin_pythoncompat__ = ">=3.7,<4"


def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = AutoselectPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": (
			__plugin_implementation__.get_update_information
		)
	}
