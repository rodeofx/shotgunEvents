Shotgun Event Daemon
====================

This software was originaly developed by `Patrick Boucher
<http://www.patrickboucher.com>`_ with support from `Rodeo Fx
<http://rodeofx.com>`_ and `Oblique <http://obliquefx.com>`_, it is now part of
`Shotgun Software <http://www.shotgunsoftware.com>`_'s `open source initiative
<https://github.com/shotgunsoftware>`_.

This software is provided under the MIT License that can be found in the LICENSE
file or here: http://www.opensource.org/licenses/mit-license.php

Contents
--------

.. toctree::
   :maxdepth: 3

   Installation <installation>
   Configuration <configuration>
   Plugins <api>
   Technical Details <techOverview>


Overview
--------

When you want to access the Shotgun event stream, the preferred way to do so it
to monitor the events table, get any new events, process them and repeat.

A lot of stuff is required for this process to work successfully, stuff that may
not have any direct bearing on the business rules that need to be applied.

The role of the framework is to keep any tedious monitoring tasks out of the
hands of the business logic implementor.

The framework is a daemon process that runs on a server and monitors the Shotgun
event stream. When events are found, the daemon hands the events out to a series
of registered plugins. Each plugin can process the event as it wishes.

The daemon handles:

- Registering plugins from one or more specified paths.
- Deactivate any crashing plugins.
- Reloading plugins when they change on disk.
- Monitoring the Shotgun event stream.
- Remembering the last processed event id and any backlog.
- Starting from the last processed event id on daemon startup.
- Catching any connection errors.
- Logging information to stdout, file or email as required.
- Creating a connection to Shotgun that will be used by the callback.
- Handing off events to registered callbacks.

A plugin handles:

- Registering any number of callbacks into the framework.
- Processing a single event when one is provided by the framework.


Advantages of the framework
---------------------------

- Only deal with a single monitoring mechanism for all scripts, not one per
  script.
- Minimize network and database load (only one monitor that supplies event to
  many event processing plugins).


Known Issues
------------

- When processing a large amount of items through a batch process. The resulting
  events may not be processed. There is code to address this but it is rather new
  and might not be completely bug free.

If you would like to submit issues please go to the `GitHub issues page
<http://github.com/shotgunsoftware/shotgunEvents/issues>`_.


Going forward
-------------

Here is some stuff that could be changed or added going forward:

- Parallelize the processing of events. A tough one considering possible event
  dependencies.
- Pass all data to the callbacks using a context object for better future
  scalability.
- Allow for late creation of the Shotgun connections on access by the callback.
- Make config reading more robust.


Indices and tables
==================

* :ref:`genindex`
* :ref:`search`
