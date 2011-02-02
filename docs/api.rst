Plugin API
==========


Plugin file
-----------

A plugin file is any *.py* file in a plugin path as specified in the config file.

To be loaded by the framework, your plugin should at least implement the following function.

.. function:: registerCallbacks(reg)

	:param reg: The :class:`Registrar` you will interact with to tell the framework which functions to call.


Registrar
---------

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

	.. method:: registerCallback(sgScriptName, sgScriptKey, callback, args=None, matchEvents=None)

		Register a callback into the engine for this plugin.

		:param str sgScriptName: The name of the script taken from the Shotgun scripts page.
		:param str sgScriptKey: The application key for the script taken from a Shotgun script page.
		:param callback: A callable function that. See :ref:`callback`.
		:param args: Any object you want the framework to pass back into your callback.
		:param dict matchEvents: A filter of events you want to have passed to your callback.

		If no *matchEvent* filter is specified or None is specified, all events
		will be passed to the callback. Otherwise each key in the *matchEvents*
		filter is an event_type while each value is a list of possible
		attribute_name::

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

		.. note::

			The point of the *args* argument is for you to be able to process
			time consuming stuff in the :func:`registerCallbacks` function and
			have it passed back to you at event processing time.

		.. note::
			Another use of the *args* argument could be to pass in a common
			mutable, say a `dict`, to multiple callbacks to have them share
			data.


Callback
--------


A callback that will be registered with the system must take four arguments:

- A Shotgun connection instance if you need to query Shotgun for additional
  information.
- A Python Logger object that should be used for reporting. Error and Critical
  messages will be sent via email to any configured user.
- The Shotgun event to be processed.
- The *args* value passed in at callback registration time.

.. warning::

	You can do whatever you want in a plugin but if any exception raises back to
	the framework. The plugin within which the offending callback lives will be
	deactivated until the file on disk is changed.
