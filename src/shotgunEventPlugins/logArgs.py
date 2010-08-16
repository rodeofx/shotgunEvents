"""

Shotgun event processing plugin
-------------------------------

A Shotgun event processing plugin has two main parts. A callback registration
function and any number of callbacks.

registerCallbacks function.
===========================

    >>> def registerCallbacks(reg):
    ...     ...

This function tells the event processing system which functions to call to
process events.

This function should take one argument which is a Registrar object.

The Registrar has one method: registerCallback(name, key, callback, args)

    name: script name as stored in Shotgun.
    key: script key as stored in Shotgun.
    callback: the function object you wish to be called to process events.
    args: an object that will be passed as is to your callback.

For each of your functions that should process Shotgun events, call
reg.registerCallback once with the appropriate arguments.

You can register as many functions as you wish and not all functions need to be
registered as event processing callbacks.


Callbacks
=========

Any callback function should take three arguments.

    sg: a Shotgun object instance onto which you can do queries.
    event: an event object to process.
    arg: an arbitrary argument that was provided at callback registration.


Printing out information
========================

Using the print statement in an event plugin is not recommended. It is prefered
you use the standard logging module from the Python standard library, like so:

    > import logging
    > _log = logging.getLogger('myPluginName')
    > _log.info('info message')

If the event framework is running as a daemon this will be logged to a file
otherwise it will be logged to stdout.

"""

import logging

_log = logging.getLogger('logArgs')


def registerCallbacks(reg):
    """Register all necessary or appropriate callbacks for this plugin.

    The $DEMO_SCRIPT_NAME$ and $DEMO_API_KEY$ placeholders need to be changed
    for appropriate values. All callbacks can share script names and api keys,
    they can also all each have their own set of credentials or anything in
    between.
    """
    reg.registerCallback('$DEMO_SCRIPT_NAME$', '$DEMO_API_KEY$', logArgs, None)


def logArgs(sg, event, args):
    """A callback that logs its arguments."""
    _log.debug("%s" % str(event))
