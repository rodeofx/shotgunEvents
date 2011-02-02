Technical Overview
==================


Plugin processing order
-----------------------

Each event is always processed in the same predictable order so if any plugins
or callbacks are co-dependant, your can safely organize their processing.

The configuration file specifies a *paths* config that contains one or multiple
plugin locations. The earlier the location in the list the earlier the contained
plugins will be processed.

Each plugin within a plugin path is then processed in ascending alphabetical order.

.. note::

	Internally the filenames are put in a list and sorted.

Finally, each callback registered by a plugin is called in registration order.
First resgistered, first run.

It is suggested to keep any functionality that needs to share state somehow in
the same plugin as one or multiple callbacks.


Registering a plugin
--------------------

When the daemon loads, it looks in defined plugin locations and tries to import
any .py file. If a .py file has a *registerCallbacks* function, it is called,
passing in a Registrar object. The Registrar is what is used to do the callback
registrations.

Here is an example of a *registerCallbacks* function::

	def registerCallbacks(reg):
	    reg.registerCallback('name', 'apiKey', doEvent)

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

Here is an example of a functional callback::

	def doEvent(sg, logger, event, args):
	    logger.info('In event %s...', str(event))


Logging information
-------------------

All information can be passed out of the system (framework or plugins) by using
the provided logger objects that come from the Python logging framework and are
configured appropriately for you.

To log from the registerCallbacks function do as follows::

	def registerCallbacks(reg):
	    reg.logger.info('info')
	    reg.logger.error('error') # levels error and higher will be sent via email.

To log from a callback function::

	def myRegisteredCallback(sg, logger, event, args):
	    logger.info('In callback...')
