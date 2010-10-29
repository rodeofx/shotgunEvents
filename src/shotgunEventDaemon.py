#!/usr/bin/python
"""
Shotgun Event Framework
=======================

Overview
--------

When you want to access the Shotgun event stream, the preferred way to do so it
to poll the events table, get any new events, process them and repeat.

A lot of stuff is required for this process to work successfully, stuff that may
not have any direct bearing on the business rules that need to be applied.

The role of the framework is to keep any tedious event polling related tasks out
of the hands of the business logic implementor.

The framework is a daemon process that runs on a server and polls the Shotgun
event stream. When events are found, the daemon hands the events out to a series
of registered plugins. Each plugin can process the event as it wishes.

The daemon handles:

- Registering plugins from one or more specified paths.
- Reloading plugins when they change on disk.
- Polling the Shotgun event stream.
- Remembering the last processed event id.
- Starting from the last processed event id on daemon startup.
- Catching any connection errors.
- Logging information to stdout, file or email as required.
- Creating a connection to Shotgun that will be used by the callback.
- Handing off events to registered callbacks.

A plugin handles:

- Registering any number of callbacks into the framework.
- Processing a single event when one is provided by the framework.

Registering a plugin
--------------------

When the daemon loads, it looks in defined plugin locations and tries to import
any .py file. If a .py file has a *registerCallbacks* function, it is called,
passing in a Registrar object. The Registrar is what is used to do the callback
registrations.

Here is an example of a *registerCallbacks* function:

	>>> def registerCallbacks(reg):
	...     reg.registerCallback('name', 'apiKey', doEvent)

The registerCallback method of the Registrar object requires three arguments:

- A script name (as per Shotgun)
- A script API key (as per Shotgun)
- A callback to provide events to for processing

Optionally, you can also provide an argument that will be passed on to the
processing callback.

A callback
----------

A callback requires four arguments:

- A shotgun instance with which to fetch any required information
- A logger object used to log messages.
- The event to process
- Any extra arguments provided at registration time

Here is an example of a functional callback:

	>>> def doEvent(sg, logger, event, args):
	...     logger.info('In event %s...', str(event))

Logging information
-------------------

All information can be passed out of the system (framework or plugins) by using
the provided logger objects that come from the Python logging framework but are
configured appropriately for you.

To log from the registerCallbacks function do as follows:

	>>> def registerCallbacks(reg):
	...     reg.logger.info('info')
	...     reg.logger.error('error') # levels error and higher will be sent via email.

To log from a callback function:

	>>> def myRegisteredCallback(sg, logger, event, args):
	...     logger.info('In callback...')

Advantages of the framework
---------------------------

- Only deal with a single polling mechanism, not with polling in many different
  scripts.
- Minimize network and database load (only one poller that supplies event to
  many event processing plugins).

Going forward
-------------

Here is some stuff that could be changed or added going forward:

- Parallelize the processing of events
- Pass all data to the callbacks using a context object for better future
  scalability.
- Allow for late creation of the Shotgun connections on access by the callback
- Make config reading more robust
"""

import ConfigParser
import imp
import logging
import logging.handlers
import os
import pprint
import socket
import sys
import time
import types
import traceback

import daemonizer
import shotgun_api3 as sg


class LogFactory(object):
	"""
	Logging control and configuration.

	@cvar EMAIL_FORMAT_STRING: The template for an error when sent via email.
	"""
	EMAIL_FORMAT_STRING = """Time: %(asctime)s
Logger: %(name)s
Path: %(pathname)s
Function: %(funcName)s
Line: %(lineno)d

%(message)s"""

	def __init__(self, config):
		"""
		@param config: The base configuration options for this L{LogFactory}.
		@type config: I{ConfigParser.ConfigParser}
		"""
		self._loggers = []

		# Get configuration options
		self._smtpServer = config.get('emails', 'server')
		self._fromAddr = config.get('emails', 'from')
		self._toAddrs = [s.strip() for s in config.get('emails', 'to').split(',')]
		self._subject = config.get('emails', 'subject')
		self._username = None
		self._password = None
		if config.has_option('emails', 'username'):
			self._username = config.get('emails', 'username')
		if config.has_option('emails', 'password'):
			self._password = config.get('emails', 'password')
		self._loggingLevel = config.getint('daemon', 'logging')

		# Setup the file logger at the root
		loggingPath = config.get('daemon', 'logFile')
		logger = self.getLogger()
		logger.setLevel(self._loggingLevel)
		handler = logging.handlers.TimedRotatingFileHandler(loggingPath, 'midnight', backupCount=10)
		handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
		logger.addHandler(handler)

	def getLogger(self, namespace=None, emails=False):
		"""
		Create and configure a logger later use.

		@note: If a logger for a given namespace has allready been configured in
			a specific manner, a second call to this function with the same
			namespace will completely reconfigure the logger.

		@param namespace: The dot delimited namespace of the logger.
		@type namespace: I{str}
		@param emails: An indication of how you want the email behavior of this
			logger to be configured. True will use default email addresses,
			False will not configure any emailing while a list of addresses
			will override any default ones.
		@type emails: A I{list}/I{tuple} of email addresses or I{bool}.
		"""
		logger = logging.getLogger(namespace)

		# Configure the logger
		if emails is False:
			self.removeHandlersFromLogger(logger, logging.handlers.SMTPHandler)
		elif emails is True:
			self.addMailHandlerToLogger(logger, self._toAddrs)
		elif isinstance(emails, (list, tuple)):
			self.addMailHandlerToLogger(logger, emails)
		else:
			msg = 'Argument emails should be True to use the default addresses, False to not send any emails or a list of recipient addresses. Got %s.'
			raise ValueError(msg % type(emails))

		return logger

	@staticmethod
	def removeHandlersFromLogger(logger, handlerTypes=None):
		"""
		Remove all handlers or handlers of a specified type from a logger.

		@param logger: The logger who's handlers should be processed.
		@type logger: A logging.Logger object
		@param handlerTypes: A type of handler or list/tuple of types of handlers
			that should be removed from the logger. If I{None}, all handlers are
			removed.
		@type handlerTypes: L{None}, a logging.Handler subclass or
			I{list}/I{tuple} of logging.Handler subclasses.
		"""
		for handler in logger.handlers:
			if handlerTypes is None or isinstance(handler, handlerTypes):
				logger.removeHandler(handler)

	def addMailHandlerToLogger(self, logger, toAddrs):
		"""
		Configure a logger with a handler that sends emails to specified
		addresses.

		The format of the email is defined by L{LogFactory.EMAIL_FORMAT_STRING}.

		@note: Any SMTPHandler already connected to the logger will be removed.

		@param logger: The logger to configure
		@type logger: A logging.Logger instance
		@param toAddrs: The addresses to send the email to.
		@type toAddrs: A list of email addresses that will be passed on to the
			SMTPHandler.
		"""
		self.removeHandlersFromLogger(logger, logging.handlers.SMTPHandler)

		if self._smtpServer and self._fromAddr and toAddrs and self._subject:
			if self._username and self._password:
				mailHandler = CustomSMTPHandler(self._smtpServer, self._fromAddr, toAddrs, self._subject, (self._username, self._password))
			else:
				mailHandler = CustomSMTPHandler(self._smtpServer, self._fromAddr, toAddrs, self._subject)

			mailHandler.setLevel(logging.ERROR)
			mailFormatter = logging.Formatter(self.EMAIL_FORMAT_STRING)
			mailHandler.setFormatter(mailFormatter)

			logger.addHandler(mailHandler)


class Engine(object):
	"""
	The engine holds the main loop of event processing.
	"""

	def __init__(self, logFactory, config):
		"""
		@param logFactory: A L{LogFactory} capable of supplying properly
			configured logger objects.
		@type logFactory: L{LogFactory}
		@param config: The base configuration options for this L{Engine}.
		@type config: I{ConfigParser.ConfigParser}
		"""
		self._modules = {}
		self._logFactory = logFactory
		self._log = self._logFactory.getLogger('engine', emails=True)
		self._lastEventId = None

		# Get config values
		self._paths = [s.strip() for s in config.get('plugins', 'paths').split(',')]
		self._server = config.get('shotgun', 'server')
		self._sg = sg.Shotgun(self._server, config.get('shotgun', 'name'), config.get('shotgun', 'key'))
		self._pidFile = config.get('daemon', 'pidFile')
		self._eventIdFile = config.get('daemon', 'eventIdFile')

	def getShotgunURL(self):
		"""
		Get the URL of the Shotgun instance this engine will be polling.

		@return: A url to a Shotgun instance.
		@rtype: I{str}
		"""
		return self._server

	def getPluginLogger(self, namespace, emails=False):
		"""
		Get a logger properly setup for a plugin's use.

		@note: The requested namespace will be prefixed with "plugin.".

		@param namespace: The namespace of the logger in the logging hierarchy.
		@type namespace: I{str}
		@param emails: See L{LogFactory.getLogger}'s emails argument for info.
		@type emails: A I{list}/I{tuple} of email addresses or I{bool}.

		@return: A pre-configured logger.
		@rtype: I{logging.Logger}
		"""
		return self._logFactory.getLogger('plugin.' + namespace, emails)

	def start(self):
		"""
		Start the processing of events.

		If a pidFile (see .conf file) is present, the engine will not start,
		otherwise one will be created and will store the process id of the
		engine.

		Once the pid file is taken care of, the last processed id is loaded up
		from persistent storage on disk.

		Finally the main loop is started.

		If a KeyboardInterrupt or other general Exception is raised. The engine
		will try to cleanup after itself and remove the pidFile.
		"""
		if self._pidFile:
			if os.path.exists(self._pidFile):
				self._log.critical('The pid file (%s) allready exists. Is another event sink running?', self._pidFile)
				return

			fh = open(self._pidFile, 'w')
			fh.write("%d\n" % os.getpid())
			fh.close()

		self._loadLastEventId()

		try:
			self._mainLoop()
		except KeyboardInterrupt, ex:
			self._log.warning('Keyboard interrupt. Cleaning up...')
		except Exception, ex:
			self._log.critical('Crash!!!!! Unexpected error (%s) in main loop.\n\n%s', type(ex), traceback.format_exc(ex))
		finally:
			self._removePidFile()

	def _loadLastEventId(self):
		"""
		Load the last processed event id from the disk

		If no event has ever been processed or if the eventIdFile has been
		deleted from disk, no id will be recoverable. In this case, we will try
		contacting Shotgun to get the latest event's id and we'll start
		processing from there.
		"""
		if self._eventIdFile and os.path.exists(self._eventIdFile):
			try:
				fh = open(self._eventIdFile)
				line = fh.readline()
				if line.isdigit():
					self._saveEventId(int(line))
					self._log.debug('Read last event id (%d) from file.', self._lastEventId)
				fh.close()
			except OSError, ex:
				self._log.error('Could not load event id from file.\n\n%s', traceback.format_exc(ex))

		if self._lastEventId is None:
			order = [{'column':'created_at', 'direction':'desc'}]
			result = self._sg.find_one("EventLogEntry", filters=[], fields=['id'], order=order)
			self._log.info('Read last event id (%d) from the Shotgun database.', result['id'])
			self._saveEventId(result['id'])

	def _mainLoop(self):
		"""
		Run the event processing loop.

		General behavior:
		- Load plugins from disk - see L{load} method.
		- Get new events from Shotgun
		- Loop through events
		- Loop through each plugin
		- Loop through each callback
		- Send the callback an event
		- Once all callbacks are done in all plugins, save the eventId
		- Go to the next event
		- Once all events are processed, wait one second and start over.

		Caveats:
		- If a plugin is deemed "inactive" (an error occured during
		  registration), skip it.
		- If a callback is deemed "inactive" (an error occured during callback
		  execution), skip it.
		- Each time through the loop, if the pidFile is gone, stop.
		"""
		self._log.debug('Starting the event processing loop.')
		while self._checkContinue():
			self.load()
			for event in self._getNewEvents():
				for module in self._modules.values():
					if module.isActive():
						for callback in module:
							if callback.isActive():
								msg = 'Dispatching event %d to callback %s in plugin %s.'
								self._log.debug(msg, event['id'], str(callback), str(module))
								callback.process(event)
							else:
								msg = 'Skipping inactive callback %s in plugin.'
								self._log.debug(msg, str(callback), str(module))
					else:
						self._log.debug('Skipping inactive module %s.', str(module))
				self._saveEventId(event['id'])
			time.sleep(1)
		self._log.debug('Shuting down event processing loop.')

	def stop(self):
		"""
		Stop the processing of events.

		On each iteration of the main loop, we check if the pidFile exists. If
		it doesn't, we stop processing events. That's our kill switch. So to
		stop event processing from this method, we just delete the pidFile from
		the filesystem.
		"""
		self._removePidFile()
		self._log.info('Stopping gracefully once current events have been processed.')

	def load(self):
		"""
		Load plugins from disk.

		General behavior:
		- Loop on all paths.
		- Find all valid .py plugin files.
		- Loop on all plugin files.
		- For any new plugins, load them, otherwise, refresh them.
		"""
		newModules = {}

		for path in self._paths:
			if not os.path.isdir(path):
				continue

			for basename in os.listdir(path):
				if not basename.endswith('.py') or basename.startswith('.'):
					continue

				filePath = os.path.join(path, basename)
				if filePath in self._modules:
					newModules[filePath] = self._modules[filePath]
				else:
					newModules[filePath] = Module(self, filePath)

				newModules[filePath].load()

		self._modules = newModules

	def _checkContinue(self):
		"""
		Check if this engine should still be processing events.

		As long as the pidFile exists on disk, this engine should keep
		processing events.

		@return: True if processing should continue, False otherwise.
		@rtype: I{bool}
		"""
		if self._pidFile is None:
			return True

		if os.path.exists(self._pidFile):
			return True

		return False

	def _getNewEvents(self):
		"""
		Fetch new events from Shotgun.

		@return: Recent events that need to be processed by the engine.
		@rtype: I{list} of Shotgun event dictionaries.
		"""
		filters = [['id', 'greater_than', self._lastEventId]]
		fields = ['id', 'event_type', 'attribute_name', 'meta', 'entity', 'user', 'project']
		order = [{'column':'created_at', 'direction':'asc'}]

		while True:
			try:
				events = self._sg.find("EventLogEntry", filters=filters, fields=fields, order=order, filter_operator='all')
				return events
			except (sg.ProtocolError, sg.ResponseError), ex:
				self._log.warning(str(ex))
				time.sleep(60)
			except socket.timeout, ex:
				self._log.error('Socket timeout. Will retry. %s', str(ex))

		return []

	def _saveEventId(self, eid):
		"""
		Save an event Id to persistant storage.

		Next time the engine is started it will try to read the event id from
		this location to know at which event it should start processing.
		"""
		self._lastEventId = eid
		if self._eventIdFile is not None:
			try:
				fh = open(self._eventIdFile, 'w')
				fh.write('%d' % eid)
				fh.close()
			except OSError, ex:
				self._log.error('Can not write event eid to %s.\n\n%s', self._eventIdFile, traceback.format_exc(ex))

	def _removePidFile(self):
		"""
		Remove the pidFile from the disk.

		This will make the engine stop next time through the main loop if it is
		still processing events.
		"""
		if self._pidFile and os.path.exists(self._pidFile):
			try:
				os.unlink(self._pidFile)
			except OSError, ex:
				self._log.error('Error removing pid file.\n\n%s', traceback.format_exc(ex))


class Module(object):
	"""
	The module class represents a loadable plugin.

	@todo: Rename this class Plugin to make things clearer.
	"""
	def __init__(self, engine, path):
		"""
		@param engine: The engine that instanciated this plugin.
		@type engine: L{Engine}
		@param path: The path of the plugin file to load.
		@type path: I{str}

		@raise ValueError: If the path to the plugin is not a valid file.
		"""
		self._engine = engine
		self._path = path

		if not os.path.isfile(path):
			raise ValueError('The path to the module is not a valid file - %s.' % path)

		self._moduleName = os.path.splitext(os.path.split(self._path)[1])[0]
		self._active = True
		self._emails = True
		self._logger = self._engine.getPluginLogger(self._moduleName, self._emails)
		self._callbacks = []
		self._mtime = None

		self.load()

	def isActive(self):
		"""
		Is the current plugin active. Should it's callbacks be run?

		@return: True if this plugin's callbacks should be run, False otherwise.
		@rtype: I{bool}
		"""
		return self._active

	def setEmails(self, emails):
		"""
		Set the email addresses to whom this plugin should send errors.

		@param emails: See L{LogFactory.getLogger}'s emails argument for info.
		@type emails: A I{list}/I{tuple} of email addresses or I{bool}.
		"""
		if emails != self._emails:
			self._emails = emails
			self._logger = self._engine.getPluginLogger(self._moduleName, self._emails)

	def getLogger(self):
		"""
		Get the logger for this plugin.

		@return: The logger configured for this plugin.
		@rtype: L{logging.Logger}
		"""
		return self._logger

	def load(self):
		"""
		Load/Reload the plugin and all its callbacks.

		If a plugin has never been loaded it will be loaded normally. If the
		plugin has been loaded before it will be reloaded only if the file has
		been modified on disk. In this event callbacks will all be cleared and
		reloaded.
		"""
		mtime = os.path.getmtime(self._path)
		if self._mtime is None:
			self._load(self._moduleName, mtime, 'Loading module at %s' % self._path)
		elif self._mtime < mtime:
			self._load(self._moduleName, mtime, 'Reloading module at %s' % self._path)

	def _load(self, moduleName, mtime, message):
		"""
		Implements the load/reload specifics.

		General behavior:
		- Try to load the source of the plugin.
		- Try to find a function called registerCallbacks in the file.
		- Try to run the registration function.

		At every step along the way, if any error occurs the whole module will
		be deactivated and the function will return.
		"""
		self.getLogger().info(message)
		self._mtime = mtime
		self._callbacks = []
		self._active = True

		try:
			module = imp.load_source(moduleName, self._path)
		except BaseException, ex:
			self._active = False
			self._logger.error('Could not load the module at %s.\n\n%s', self._path, traceback.format_exc(ex))
			return

		regFunc = getattr(module, 'registerCallbacks', None)
		if isinstance(regFunc, types.FunctionType):
			try:
				regFunc(Registrar(self))
			except BaseException, ex:
				self.getLogger().critical('Error running register callback function from module at %s.\n\n%s', self._path, traceback.format_exc(ex))
				self._active = False
		else:
			self.getLogger().critical('Did not find a registerCallbacks function in module at %s.', self._path)
			self._active = False

	def registerCallback(self, sgScriptName, sgScriptKey, callback, args=None):
		"""
		Register a callback in the module.
		"""
		global sg
		sgConnection = sg.Shotgun(self._engine.getShotgunURL(), sgScriptName, sgScriptKey)
		logger = self._engine.getPluginLogger(self._moduleName + '.' + callback.__name__, False)
		self._callbacks.append(Callback(callback, sgConnection, logger, args))

	def __iter__(self):
		"""
		A plugin is iterable and will iterate over all its L{Callback} objects.
		"""
		return self._callbacks.__iter__()

	def __str__(self):
		"""
		Provide the name of the plugin when it is cast as string.

		@return: The name of the plugin.
		@rtype: I{str}
		"""
		return self._moduleName


class Registrar(object):
	"""
	Object used to register callbacks into the system by a plugin's registration
	function.
	"""
	def __init__(self, module):
		"""
		@param module: The module that is being registered.
		@type module: L{Module}
		"""
		self._module = module

	def getLogger(self):
		"""
		Get the logger used to log messages from within the plugin.

		@return: A properly configured logger object.
		@rtype: I{logging.Logger}
		"""
		return self._module.getLogger()

	logger = property(getLogger)

	def setEmails(self, *emails):
		"""
		Set the emails that should receive error and critical notices when
		something bad happens in this module or any of its callbacks.

		To send emails to default addresses (default):

		>>> reg.setEmails(True)

		To disable emails (this is not suggested as you won't get error messages):

		>>> reg.setEmails(False)

		To send emails to specific addresses use:

		>>> reg.setEmails('user1@domain.com', 'user2@domain.com')

		@param emails: See L{LogFactory.getLogger}'s emails argument for info.
		@type emails: A I{list}/I{tuple} of email addresses or I{bool}.
		"""
		self._module.setEmails(emails)

	def registerCallback(self, sgScriptName, sgScriptKey, callback, args=None):
		"""
		Register a callback into the engine for this plugin.

		@note: The args argument will be stored and returned to you when the
			callback is run. This is to allow you the possibility of gathering
			data in the registration part of the process and have access to said
			data when the callback is run.

		@param sgScriptName: A script name as configured in Shotgun.
		@type sgScriptName: I{str}
		@param sgScriptKey: A script key as configured in Shotgun.
		@type sgScriptKey: I{str}
		@param callback: The function to run when a Shotgun event occurs.
		@type callback: A function object.
		@param args: Any datastructure you would like to be passed to your
			callback function. Defaults to None.
		@type args: Any object.
		"""
		self._module.registerCallback(sgScriptName, sgScriptKey, callback, args)


class Callback(object):
	"""
	A part of a plugin that can be called to process a Shotgun event.
	"""

	def __init__(self, callback, shotgun, logger, args=None):
		"""
		@param callback: The function to run when a Shotgun event occurs.
		@type callback: A function object.
		@param shotgun: The Shotgun instance that will be used to communicate
			with your Shotgun server.
		@type shotgun: L{sg.Shotgun}
		@param logger: An object to log messages with.
		@type logger: I{logging.Logger}
		@param args: Any datastructure you would like to be passed to your
			callback function. Defaults to None.
		@type args: Any object.

		@raise TypeError: If the callback is not a callable object.
		"""
		if not callable(callback):
			raise TypeError('The callback must be a callable object (function, method or callable class instance).')

		self._shotgun = shotgun
		self._callback = callback
		self._logger = logger
		self._args = args
		self._active = True

	def process(self, event):
		"""
		Process an event with the callback object supplied on initialization.

		If an error occurs, it will be logged appropriately and the callback
		will be deactivated.

		@param event: The Shotgun event to process.
		@type event: I{dict}
		"""
		try:
			self._callback(self._shotgun, self._logger, event, self._args)
		except BaseException, ex:
			msg = 'An error occured processing an event.\n\nEvent Data:\n%s\n\n%s'
			self._logger.critical(msg, pprint.pformat(event), traceback.format_exc(ex))
			self._active = False

	def isActive(self):
		"""
		Check if this callback is active, i.e. if events should be passed to it
		for processing.

		@return: True if this callback should process events, False otherwise.
		@rtype: I{bool}
		"""
		return self._active

	def __str__(self):
		"""
		The name of the callback.

		@return: The name of the callback
		@rtype: I{str}
		"""
		return self._callback.__name__


class CustomSMTPHandler(logging.handlers.SMTPHandler):
	"""
	A custom SMTPHandler subclass that will adapt it's subject depending on the
	error severity.
	"""

	LEVEL_SUBJECTS = {
		logging.ERROR: 'ERROR - Shotgun event daemon.',
		logging.CRITICAL: 'CRITICAL - Shotgun event daemon.',
	}

	def getSubject(self, record):
		subject = logging.handlers.SMTPHandler.getSubject(self, record)
		if record.levelno in self.LEVEL_SUBJECTS:
			return subject + ' ' + self.LEVEL_SUBJECTS[record.levelno]
		return subject


def main():
	daemonize = True
	configPath = _getConfigPath()
	if not os.path.exists(configPath):
		print 'Config path not found!'
		return 1

	if daemonize:
		# Double fork to detach process
		daemonizer.createDaemon()
	else:
		# Setup the stdout logger
		handler = logging.StreamHandler()
		handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
		logging.getLogger().addHandler(handler)

	# TODO: Take value from config
	socket.setdefaulttimeout(60)

	# Read/parse the config
	config = ConfigParser.ConfigParser()
	config.read(configPath)

	# Prep logging.
	logFactory = LogFactory(config)

	# Notify which version of shotgun api we are using
	logFactory.getLogger().debug('Using Shotgun version %s' % sg.__version__)

	# Start the event processing engine.
	engine = Engine(logFactory, config)
	engine.start()

	return 0


def _getConfigPath():
	"""
	Get the path of the shotgunEventDaemon configuration file.
	"""
	paths = ['$CONFIG_PATH$', '/etc/shotgunEventDaemon.conf']
	for path in paths:
		if os.path.exists(path):
			return path
	return None


if __name__ == '__main__':
	sys.exit(main())
