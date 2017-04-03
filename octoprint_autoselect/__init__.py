# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import octoprint.events
from octoprint.filemanager.destinations import FileDestinations

class AutoselectPlugin(octoprint.plugin.EventHandlerPlugin):
	def __init__(self):
		self._event = None
		if hasattr(octoprint.events.Events, "FILE_ADDED"):
			# OctoPrint >= 1.3.3: we can monitor the FileAdded event as triggered
			# by the file manager
			self._event = octoprint.events.Events.FILE_ADDED
			def to_storage_and_name(payload):
				return payload["storage"], payload["path"]
		else:
			# OctoPrint < 1.3.3: we can only react to the upload event, files added
			# through e.g. the watched folder or other means than the REST API are
			# left out. See also #1
			self._event = octoprint.events.Events.UPLOAD
			def to_storage_and_name(payload):
				return payload["target"], payload["path"]

		self._to_storage_and_name = to_storage_and_name

	def on_event(self, event, payload):
		if event != self._event:
			return

		if not self._printer.is_ready():
			self._logger.debug("Printer is not ready, not autoselecting uploaded file")
			return

		storage, filename = self._to_storage_and_name(payload)

		if storage == FileDestinations.SDCARD:
			path = filename
			sd = True
		else:
			path = self._file_manager.path_on_disk(storage, filename)
			sd = False

		self._logger.info("Selecting {} on {} that was just uploaded".format(filename, storage))
		self._printer.select_file(path, sd, False)

__plugin_name__ = "Autoselect Plugin"

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = AutoselectPlugin()
