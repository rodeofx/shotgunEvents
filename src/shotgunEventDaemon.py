#!/usr/bin/python

import ConfigParser
import imp
import logging
import logging.handlers
import os
import sys
import time
import types
import traceback

import daemonizer
import shotgun_api3 as sg


class Engine(object):
    def __init__(self, pluginPaths, server, name, key, pidFile=None, eventIdFile=None):
        self._modules = {}
        self._paths = pluginPaths
        self._server = server
        self._sg = sg.Shotgun(self._server, name, key)
        self._pidFile = pidFile
        self._eventIdFile = eventIdFile
        self._lastEventId = None

    def start(self):
        if self._pidFile:
            if os.path.exists(self._pidFile):
                logging.critical('The pid file (%s) allready exists. Is another event sink running?', self._pidFile)
                return

            fh = open(self._pidFile, 'w')
            fh.write("%d\n" % os.getpid())
            fh.close()

        self._loadLastEventId()

        try:
            self._mainLoop()
        except KeyboardInterrupt, e:
            logging.warning('Keyboard interrupt. Cleaning up...')
        except Exception, e:
            logging.critical('Crash!!!!! Unexpected error in main loop.\n\n%s', traceback.format_exc(e))
        finally:
            self._removePidFile()

    def _loadLastEventId(self):
        if self._eventIdFile and os.path.exists(self._eventIdFile):
            try:
                fh = open(self._eventIdFile)
                line = fh.readline()
                if line.isdigit():
                    self._saveEventId(int(line))
                    logging.debug('Read last event id (%d) from file.', self._lastEventId)
                fh.close()
            except OSError, e:
                logging.error('Could not load event id from file.\n\n%s', traceback.format_exc(e))

        if self._lastEventId is None:
            result = self._sg.find_one("EventLogEntry", filters=[], fields=['id'], order=[{'column':'created_at', 'direction':'desc'}])
            logging.info('Read last event id (%d) from the Shotgun database.', result['id'])
            self._saveEventId(result['id'])

    def _mainLoop(self):
        logging.debug('Starting the event processing loop.')
        while self._checkContinue():
            self.load()
            for event in self._getNewEvents():
                for module in self._modules.values():
                    if module.isActive:
                        for callback in module:
                            if callback.isActive():
                                callback.process(event)
                self._saveEventId(event['id'])
            time.sleep(1)
        logging.debug('Shuting down event processing loop.')

    def stop(self):
        self._removePidFile()
        logging.info('Stopping gracefully once current events have been processed.')

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
                    module = Module(self._server, filePath)
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
        fields = ['id', 'event_type', 'attribute_name', 'meta', 'entity']
        order = [{'column':'created_at', 'direction':'asc'}]

        try:
            return self._sg.find("EventLogEntry", filters=filters, fields=fields, order=order, filter_operator='all')
        except (sg.ProtocolError, sg.ResponseError), e:
            logging.warning(str(e))

        return []

    def _saveEventId(self, eid):
        self._lastEventId = eid
        if self._eventIdFile is not None:
            try:
                fh = open(self._eventIdFile, 'w')
                fh.write('%d' % eid)
                fh.close()
            except OSError, e:
                logging.error('Can not write event eid to %s.\n\n%s', self._eventIdFile, traceback.format_exc(e))

    def _removePidFile(self):
        if self._pidFile and os.path.exists(self._pidFile):
            try:
                os.unlink(self._pidFile)
            except OSError, e:
                logging.error('Error removing pid file.\n\n%s', traceback.format_exc(e))


class Module(object):
    def __init__(self, server, path):
        self._active = True
        self._server = server
        self._path = path
        self._callbacks = []
        self._mtime = None
        self.load()

    def isActive(self):
        return self._active

    def load(self):
        dirname, basename = os.path.split(self._path)
        moduleName = os.path.splitext(basename)[0]

        mtime = os.path.getmtime(self._path)
        if self._mtime is None:
            self._load(moduleName, mtime, 'Loading module at %s' % self._path)
        elif self._mtime < mtime:
            self._load(moduleName, mtime, 'Reloading module at %s' % self._path)

    def _load(self, moduleName, mtime, message):
        logging.info(message)
        self._mtime = mtime
        self._callbacks = []
        self._active = True

        try:
            module = imp.load_source(moduleName, self._path)
        except Exception, e:
            self._active = False
            logging.error('Could not load the module at %s.\n\n%s', self._path, traceback.format_exc(e))
            return

        regFunc = getattr(module, 'registerCallbacks', None)
        if isinstance(regFunc, types.FunctionType):
            try:
                regFunc(Registrar(self))
            except Exception, e:
                logging.error('Error running register callback function from module at %s.\n\n%s', self._path, traceback.format_exc(e))
                self._active = False
        else:
            logging.error('Did not find a registerCallbacks function in module at %s.', self._path)
            self._active = False

    def registerCallback(self, sgScriptName, sgScriptKey, callback, args=None):
        global sg
        self._callbacks.append(Callback(sg.Shotgun(self._server, sgScriptName, sgScriptKey), callback, args))

    def __iter__(self):
        return self._callbacks.__iter__()


class Registrar(object):
    def __init__(self, module):
        self._module = module

    def registerCallback(self, sgScriptName, sgScriptKey, callback, args=None):
        self._module.registerCallback(sgScriptName, sgScriptKey, callback, args)


class Callback(object):
    def __init__(self, sg, callback, args=None):
        if not callable(callback):
            raise TypeError('The callback must be a callable object (function, method or callable class instance).')

        self._sg = sg
        self._callback = callback
        self._args = args
        self._active = True

    def process(self, event):
        try:
            logging.debug('Processing event %d in callback %s.', event['id'], self._callback.__name__)
            self._callback(self._sg, event, self._args)
        except Exception, e:
            logging.critical('An error occured processing an event in callback %s.\n\n%s', self._callback.__name__, traceback.format_exc(e))
            self._active = False

    def isActive(self):
        return self._active


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

    # Read/parse the config
    config = ConfigParser.ConfigParser()
    config.read(configPath)

    pidFile = config.get('daemon', 'pidFile')
    eventIdFile = config.get('daemon', 'eventIdFile')
    loggingPath = config.get('daemon', 'logFile')
    loggingLevel = config.getint('daemon', 'logging')

    server = config.get('shotgun', 'server')
    name = config.get('shotgun', 'name')
    key = config.get('shotgun', 'key')

    pluginPaths = [s.strip() for s in config.get('plugins', 'paths').split(',')]

    smtpServer = config.get('emails', 'server')
    fromAddr = config.get('emails', 'from')
    toAddrs = [s.strip() for s in config.get('emails', 'to').split(',')]
    subject = config.get('emails', 'subject')

    # Setup the file logger
    logger = logging.getLogger()
    logger.setLevel(loggingLevel)
    handler = logging.handlers.TimedRotatingFileHandler(loggingPath, 'midnight', backupCount=10)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

    # Setup the mail logger
    if smtpServer and fromAddr and toAddrs and subject:
        mailFormatter = logging.Formatter("""Time: %(asctime)s
Logger: %(name)s
Path: %(pathname)s
Function: %(funcName)s
Line: %(lineno)d

%(message)s""")
        mailHandler = CustomSMTPHandler(smtpServer, fromAddr, toAddrs, subject)
        mailHandler.setLevel(logging.ERROR)
        mailHandler.setFormatter(mailFormatter)
        logger.addHandler(mailHandler)

    # Start event processing
    engine = Engine(pluginPaths, server, name, key, pidFile, eventIdFile)
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
