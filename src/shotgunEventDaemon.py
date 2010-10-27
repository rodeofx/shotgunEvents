#!/usr/bin/python

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
    EMAIL_FORMAT_STRING = """Time: %(asctime)s
Logger: %(name)s
Path: %(pathname)s
Function: %(funcName)s
Line: %(lineno)d

%(message)s"""

    def __init__(self, config):
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
        if namespace:
            logger = logging.getLogger(namespace)
        else:
            logger = logging.getLogger()

        # Configure the logger
        if emails is False:
            self.removeHandlersFromLogger(logger, logging.handlers.SMTPHandler)
        if emails is True:
            self.addMailHandlerToLogger(logger, self._toAddrs)
        elif isinstance(emails, (list, tuple)):
            self.addMailHandlerToLogger(logger, emails)
        elif emails is not False:
            msg = 'Argument emails should be True to use the default addresses or a list of recipient addresses. Got %s.'
            raise ValueError(msg % type(emails))

        return logger

    @staticmethod
    def removeHandlersFromLogger(logger, handlerTypes=None):
        for handler in logger.handlers:
            if handlerTypes is None or isinstance(handler, handlerTypes):
                logger.removeHandler(handler)

    def addMailHandlerToLogger(self, logger, toAddrs):
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
    def __init__(self, logFactory, config):
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
        return self._server

    def getPluginLogger(self, namespace, emails=False):
        return self._logFactory.getLogger('plugin.' + namespace, emails)

    def start(self):
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
        self._log.debug('Starting the event processing loop.')
        while self._checkContinue():
            self.load()
            for event in self._getNewEvents():
                for module in self._modules.values():
                    if module.isActive():
                        for callback in module:
                            if callback.isActive():
                                callback.process(event)
                            else:
                                self._log.debug('Skipping inactive callback %s.', str(callback))
                    else:
                        self._log.debug('Skipping inactive module %s.', str(module))
                self._saveEventId(event['id'])
            time.sleep(1)
        self._log.debug('Shuting down event processing loop.')

    def stop(self):
        self._removePidFile()
        self._log.info('Stopping gracefully once current events have been processed.')

    def load(self):
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
                    newModules[filePath].load()
                else:
                    module = Module(self, filePath)
                    module.load()
                    newModules[filePath] = module

        self._modules = newModules

    def _checkContinue(self):
        if self._pidFile is None:
            return True

        if os.path.exists(self._pidFile):
            return True

        return False

    def _getNewEvents(self):
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
        self._lastEventId = eid
        if self._eventIdFile is not None:
            try:
                fh = open(self._eventIdFile, 'w')
                fh.write('%d' % eid)
                fh.close()
            except OSError, ex:
                self._log.error('Can not write event eid to %s.\n\n%s', self._eventIdFile, traceback.format_exc(ex))

    def _removePidFile(self):
        if self._pidFile and os.path.exists(self._pidFile):
            try:
                os.unlink(self._pidFile)
            except OSError, ex:
                self._log.error('Error removing pid file.\n\n%s', traceback.format_exc(ex))


class Module(object):
    def __init__(self, engine, path):
        self._moduleName = None
        self._active = True
        self._engine = engine
        self._logger = None
        self._emails = False
        self._path = path
        self._callbacks = []
        self._mtime = None
        self.load()

    def isActive(self):
        return self._active

    def setEmails(self, emails=False):
        self._logger = None
        self._emails = emails

    def getLogger(self):
        if self._logger is None:
            # Use our specified email addresses or the default email addresses.
            emails = self._emails or True
            self._logger = self._engine.getPluginLogger(self._moduleName, emails)
        return self._logger

    def load(self):
        _, basename = os.path.split(self._path)
        self._moduleName = os.path.splitext(basename)[0]

        mtime = os.path.getmtime(self._path)
        if self._mtime is None:
            self._load(self._moduleName, mtime, 'Loading module at %s' % self._path)
        elif self._mtime < mtime:
            self._load(self._moduleName, mtime, 'Reloading module at %s' % self._path)

    def _load(self, moduleName, mtime, message):
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
        global sg
        sgConnection = sg.Shotgun(self._engine.getShotgunURL(), sgScriptName, sgScriptKey)
        logger = self._engine.getPluginLogger(self._moduleName + '.' + callback.__name__, self._emails)
        self._callbacks.append(Callback(callback, sgConnection, logger, args))

    def __iter__(self):
        return self._callbacks.__iter__()

    def __str__(self):
        return self._moduleName


class Registrar(object):
    def __init__(self, module):
        self._module = module

    def getLogger(self):
        return self._module.getLogger()

    logger = property(getLogger)

    def setEmails(self, *emails):
        self._module.setEmails(emails)

    def registerCallback(self, sgScriptName, sgScriptKey, callback, args=None):
        self._module.registerCallback(sgScriptName, sgScriptKey, callback, args)


class Callback(object):
    def __init__(self, callback, shotgun, logger, args=None):
        if not callable(callback):
            raise TypeError('The callback must be a callable object (function, method or callable class instance).')

        self._shotgun = shotgun
        self._callback = callback
        self._logger = logger
        self._args = args
        self._active = True

    def process(self, event):
        try:
            self._logger.debug('Processing event %d.', event['id'])
            self._callback(self._shotgun, self._logger, event, self._args)
        except BaseException, ex:
            msg = 'An error occured processing an event.\n\nEvent Data:\n%s\n\n%s'
            self._logger.critical(msg, pprint.pformat(event), traceback.format_exc(ex))
            self._active = False

    def isActive(self):
        return self._active

    def __str__(self):
        return self._callback.__name__


class CustomSMTPHandler(logging.handlers.SMTPHandler):
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

    engine = Engine(logFactory, config)
    engine.start()

    return 0


def _getConfigPath():
    paths = ['$CONFIG_PATH$', '/etc/shotgunEventDaemon.conf']
    for path in paths:
        if os.path.exists(path):
            return path
    return None


if __name__ == '__main__':
    sys.exit(main())
