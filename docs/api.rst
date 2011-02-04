Plugins
=======

A plugin file is any *.py* file in a plugin path as specified in the config file.


Overview
--------

A Shotgun event processing plugin has two main parts. A callback registration
function and any number of callbacks.


registerCallbacks function
^^^^^^^^^^^^^^^^^^^^^^^^^^

To be loaded by the framework, your plugin should at least implement the
following function::

    def registerCallbacks(reg):
        pass

This function will be used to tell the event processing system which functions
to call to process events.

This function should take one argument which is a :class:`Registrar` object.

The :class:`Registrar` has one critically important method:
:meth:`~Registrar.registerCallback`.

For each of your functions that should process Shotgun events, call
:meth:`~Registrar.registerCallback` once with the appropriate arguments.

You can register as many functions as you wish and not all functions in the file
need to be registered as event processing callbacks.


Callbacks
^^^^^^^^^

A callback that will be registered with the system must take four arguments:

- A Shotgun connection instance if you need to query Shotgun for additional
  information.
- A Python Logger object that should be used for reporting. Error and Critical
  messages will be sent via email to any configured user.
- The Shotgun event to be processed.
- The *args* value passed in at callback registration time. (See :meth:`~Registrar.registerCallback`)

.. warning::

    You can do whatever you want in a plugin but if any exception raises back to
    the framework. The plugin within which the offending callback lives (and all
    contained callbacks) will be deactivated until the file on disk is changed
    (read: fixed).


Printing out information
^^^^^^^^^^^^^^^^^^^^^^^^

Using the print statement in an event plugin is not recommended. It is prefered
you use the standard logging module from the Python standard library. A logger
object will be provided to your various functions::

    def registerCallbacks(reg):
        reg.setEmails('root@domain.com', 'tech@domain.com') # Optional
        reg.logger.info('Info')
        reg.logger.error('Error') # ERROR and above will be sent via email in default config

and::

    def exampleCallback(sg, logger, event, args):
        logger.info('Info message')

If the event framework is running as a daemon this will be logged to a file
otherwise it will be logged to stdout.


API
---


registerCallbacks
^^^^^^^^^^^^^^^^^

A global level function in all plugins that is used to tell the framework about
event processing entry points in the plugin.

.. function:: registerCallbacks(reg)

    :param reg: The :class:`Registrar` you will interact with to tell the framework which functions to call.


Registrar
^^^^^^^^^

The object passed to the :func:`registerCallbacks` function.

.. class:: Registrar

    The Registrar is the object used to tell the framework how to interact with
    a plugin.

    .. method:: getLogger

        Get the python Logger object used to log messages from within the plugin.

        .. note::

            You can access this through the :attr:`logger` property as well.

    .. attribute:: logger

        See :meth:`getLogger`.

    .. method:: setEmails(* emails)

        Set the emails that should receive error and critical notices when
        something bad happens in this plugin or any of its callbacks.

        To send emails to default addresses as specified in the configuration file (default)::

            reg.setEmails(True)

        To disable emails (this is not suggested as you won't get error messages)::

            reg.setEmails(False)

        To send emails to specific addresses use::

            reg.setEmails('user1@domain.com')

        or::

            reg.setEmails('user1@domain.com', 'user2@domain.com')

    .. method:: registerCallback(sgScriptName, sgScriptKey, callback, matchEvents=None, args=None)

        Register a callback into the engine for this plugin.

        :param str sgScriptName: The name of the script taken from the Shotgun scripts page.
        :param str sgScriptKey: The application key for the script taken from a Shotgun script page.
        :param callback: A callable function that. See :func:`exampleCallback`.
        :type callback: A function or an object with a __call__ method.
        :param dict matchEvents: A filter of events you want to have passed to your callback.
        :param args: Any object you want the framework to pass back into your callback.

        The *sgScriptName* is used to identify the plugin to Shotgun. Any name
        can be shared across any number of callbacks or be unique for a single
        callback.

        The *sgScriptKey* is used to identify the plugin to Shotgun and should
        be the appropriate key for the specified *sgScriptName*.

        The specified *callback* object will be invoked when an event that
        matches your filter needs processing. Although any callable should be
        able to run, using a class here is not suggested. Use of a function or
        an instance with a *__call__* method is more appropriate.

        The *matchEvent* argument is a filter that allows you to specify which
        events the callback being registered is interrested in. If *matchEvents*
        is not specified or None is specified, all events will be passed to the
        callback. Otherwise each key in the *matchEvents* filter is an
        event_type while each value is a list of possible attribute_name::

            matchEvents = {
                'Shotgun_Task_Change': ['sg_status_list'],
            }

        You can have multiple event_type or attribute_names::

            matchEvents = {
                'Shotgun_Task_Change': ['sg_status_list'],
                'Shotgun_Version_Change': ['description', 'sg_status_list']
            }

        You can filter on any event_type that has a given attribute_name::

            matchEvents = {
                '*': ['sg_status_list'],
            }

        You can also filter on any attribute_name for a given event_type::

            matchEvents = {
                'Shotgun_Version_Change': ['*']
            }

        Although the following is valid and functionally equivalent to
        specifying nothing, it's just really useless::

            matchEvents = {
                '*': ['*']
            }

        The *args* argument will not be used by the event framework itself but
        will simply be passed back to your callback without any modification.

        .. note::
            The point of the *args* argument is for you to be able to process
            time consuming stuff in the :func:`registerCallbacks` function and
            have it passed back to you at event processing time.

        .. note::
            Another use of the *args* argument could be to pass in a common
            mutable, say a `dict`, to multiple callbacks to have them share
            data.


Callback
^^^^^^^^

Any plugin entry point registered by :meth:`Registrar.registerCallback` should
look like this.

.. function:: exampleCallback(sg, logger, event, args)

    :param sg: A Shotgun connection instance.
    :param logger: A Python logging.Logger object preconfigured for you.
    :param dict event: A Shotgun event to process
    :param args: The args argument specified at callback registration time.

.. note::

    Implementing a callback as a *__call__* method on an object instance is left
    as an exercise to the user.
