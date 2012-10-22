Configuration
=============

The following guide will help you configure shotgunEvents for your studio.

Most of the configuration for shotgunEvents is controlled by the ``shotgunEventDaemon.conf``
file. In this file, you'll find several settings you can modify to match your
needs. Most of them have defaults that will work fine for most studios, however
there are some settings that must be configured (specifically, your Shotgun
server url, script name, and application key so the shotgunEventDaemon can 
connect to your Shotgun server).

Edit shotgunEventDaemon.conf
****************************
Once you have installed shotgunEvents, the next step is to open the 
``shotgunEventDaemon.conf`` file in a text editor and modify the settings to 
match your studios needs. The defaults will be fine for most studios, however
there are some settings that have no defaults that will need to be provided by
you before you can run the daemon. 

The items your *must* provide are

- your Shotgun server url
- the Script name and Application key for connecting to Shotgun
- the full path to your plugins for the shotgunEventDaemon to run

Optionally, you can also specify an SMTP server and email-specific settings in
order to setup email notification for errors. While this is optional, if you 
choose to set this up, you must provide all of the configuration values in the
email section.

Shotgun Settings
----------------
Underneath the ``[shotgun]`` section, replace the default tokens with the correct
values for ``server``, ``name``, and ``key``. These should be the same values
you'd provide to a standard API script connecting to Shotgun.

Example::

    server: https://awesome.shotgunstudio.com
    name: shotgunEventDaemon
    key: e37d855f4823216575472346e0cb3e4947f6f7b1

Plugin Settings
---------------
You will need to tell the shotgunEventDaemon where to look for plugins to run.
Under the ``[plugins]`` section replace the default token with the correct 
value for ``paths``.

You can specify multiple locations (which may be useful if you have multiple
departments or repositories using the daemon). The value here must be a full
path to a readable existing directory.

Example::

    paths: /usr/local/shotgun/shotgunEvents/plugins

When you're first getting started, a good plugin to test with is the ``logArgs.py``
plugin located in the ``/usr/local/shotgun/shotgunEvents/src/examplePlugins``
directory. Copy that into the plugins folder you specified and we'll use that
for testing things.

Location of shotgunEventDaemon.conf
-----------------------------------
By default, the daemon will look for the shotgunEventDaemon.conf file in the 
same directory that shotgunEventDaemon.py is in, and in the ``/etc`` directory.
If you need to put the conf file in another directory, it's recommended you 
create a symlink to it from the current directory. 

.. note:: 

    If for some reason the above won't work for you, the search paths for the
    config file are located in the _getConfigPath() function at the bottom of
    the shotgunEventDaemon.py script


Testing the daemon
******************
Daemons can be difficult to test since they run in the background. There isn't
always an obvious way to see what they're doing. Lucky for us, the 
shotgunEventDaemon has an option to run it as a foreground process. Now that
we have done the minimum required setup, let's go ahead and test the daemon
and see how things go.

.. note::

    The default values used here may require root access (for example, to write to 
    the /var/log directory). The examples provided use are run using ``sudo`` to 
    accomodate this.

::

    $ sudo ./shotgunEventDaemon.py -foreground
    INFO:engine:Using Shotgun version 3.0.8
    INFO:engine:Loading plugin at /usr/local/shotgun/shotgunEvents/src/examplePlugins/logArgs.py
    INFO:engine:Last event id (248429) from the Shotgun database.

You should see the lines above when you start the script (some of the details
may differ obviously). If you get any errors, the script will terminate since we 
opted to run it in the foreground we'll see that happen. Some common errors are 
displayed below if you get stuck.

The ``logArgs.py`` plugin simply takes the event that occured in Shotgun and 
passes it to the logger. Not very exciting but it's a simple way to ensure that
the script is running and the plugin is working. If you're at a busy studio,
you may have already noticed a rapid stream of messages flowing by. If not,
login to your Shotgun server in your web browser and change some values or create 
something. You should see log statements printed out to your terminal window 
corresponding to the type of event you generated with your changes. 

If you don't see anything logged to the logfile, check your log-related settings 
in shotgunEventDaemon.conf to ensure that the ``logging`` value is set to log 
INFO level messages::

    logging: 20

and the logArgs plugin is also configured to show INFO level messages. There is 
a line at the end of the registerCallbacks() method that should read::

    reg.logger.setLevel(logging.INFO)

Assuming all looks good, to stop the shotgunEventDaemon process, simply type 
``<ctrl>-c`` in the terminal and you should see the script terminate.


Running the daemon
******************
Assuming all went well with your testing, we can now run the daemon as intended,
in the background.::

    $ sudo ./shotgunEventDaemon.py start

You should see no output and control should have been returned to you in the
terminal. We can make sure that things are running well in 2 ways. The first 
would be to check the running processes and see if this is one of them.::

    $ ps -aux | grep shotgunEventDaemon
    kp              4029   0.0  0.0  2435492    192 s001  R+    9:37AM   0:00.00 grep shotgunEventDaemon
    root            4020   0.0  0.1  2443824   4876   ??  S     9:36AM   0:00.02 /usr/bin/python ./shotgunEventDaemon.py start

We can see by the second line returned that the daemon is running. The first
line is matching the command we just ran. So we know it's running, but to ensure 
that it's *working* and the plugins are doing what they're supposed to, we can 
look at the log files and see if there's any output there.::

    $ sudo tail -f /var/log/shotgunEventDaemon/shotgunEventDaemon
    2011-09-09 09:42:44,003 - engine - INFO - Using Shotgun version 3.0.8
    2011-09-09 09:42:44,006 - engine - INFO - Loading plugin at /usr/local/shotgun/shotgunEvents/src/plugins/logArgs.py
    2011-09-09 09:42:44,199 - engine - DEBUG - Starting the event processing loop.

Go back to your web browser and make some changes to an entity. Then head back
to the terminal and look for output. You should see something like the following::

    2011-09-09 09:42:44,003 - engine - INFO - Using Shotgun version 3.0.8
    2011-09-09 09:42:44,006 - engine - INFO - Loading plugin at /usr/local/shotgun/shotgunEvents/src/plugins/logArgs.py
    2011-09-09 09:42:44,199 - engine - DEBUG - Starting the event processing loop.
    2011-09-09 09:45:31,228 - plugin.logArgs.logArgs - INFO - {'attribute_name': 'sg_status_list', 'event_type': 'Shotgun_Shot_Change', 'entity': {'type': 'Shot', 'name': 'bunny_010_0010', 'id': 860}, 'project': {'type': 'Project', 'name': 'Big Buck Bunny', 'id': 65}, 'meta': {'entity_id': 860, 'attribute_name': 'sg_status_list', 'entity_type': 'Shot', 'old_value': 'omt', 'new_value': 'ip', 'type': 'attribute_change'}, 'user': {'type': 'HumanUser', 'name': 'Kevin Porterfield', 'id': 35}, 'session_uuid': '450e4da2-dafa-11e0-9ba7-0023dffffeab', 'type': 'EventLogEntry', 'id': 276560}

The exact details of your output will differ, but what you should see is that
the plugin has done what it is supposed to do, that is, log the event to the
logfile. Again, if you don't see anything logged to the logfile, check your
log-related settings in shotgunEventDaemon.conf to ensure that the ``logging``
value is set to log INFO level messages and your logArgs plugin is also configured
to show INFO level messages.

A Note About Logging
--------------------

It should be noted that log rotation is a feature of the shotgun daemon. Log are
rotated at midnight every night and ten daily files are kept per plugin.

Next Steps
**********
Now you're ready to write your own plugins. There are some additional example
plugins provided in the src/examplePlugins folder in your installation. These
provide simple examples of how to build your own plugins to look for specific
events generated, and act on them, changing other values on your Shotgun instance.

You do not need to restart the daemon each time you make updates to a plugin, the
daemon will detect that the plugin has been updated and reload it automatically. 

If a plugin generates an error, it will not cause the daemon to crash. The plugin 
will be disabled until it is updated again (hopefully fixed). Any other plugins
will continue to run and events will continue to be processed. The daemon will
keep track of the last event id that the broken plugin processed successfully.
When it it updated (and fixed hopefully), the daemon will reload it and attempt
to process events starting from where that plugin left off. Assuming all is well
again, the daemon will catch the plugin up to the current event and then continue
to process events with all plugins as normal.


Common Errors
*************
The following are a few of the common errors that you can run into and how to 
resolve them. If you get really stuck, feel free to contact the Shotgun Software
team (support@shotgunsoftware.com) and we'll help you out.

**Invalid path: $PLUGIN_PATHS$**

    You need to specify the path to your plugins in the shotgunEventDaemon.conf file.

**Permission denied: '/var/log/shotgunEventDaemon'**

    The daemon couldn't open the logfile for writing.

    You may need to run the daemon with ``sudo`` or as a user that has permissions to 
    write to the log file specified by the ``logPath`` and ``logFile`` settings in
    shotgunEventDaemon.conf. (the default location is ``/var/log/shotgunEventDaemon`` 
    which is usually owned by root.

**ImportError: No module named shotgun_api3**

    The Shotgun API is not installed. Make sure it is either located in the current
    directory or it is in a directory in your PYTHONPATH.

    If you have to run as sudo and you think you have the PYTHONPATH setup correctly,
    remember that sudo resets the envirnment variables. You can edit the sudoers 
    file to preserve the PYTHONPATH or run sudo -e(?)



List of Configuration File Settings
***********************************

Daemon Settings
---------------

The following are general daemon operational settings.

**pidFile**

    The pidFile is the location where the daemon will store its process id while it
    is running. If this file is removed while the daemon is running, it will shutdown 
    cleanly after the next pass through the event processing loop.

    The directory must already exist and be writable. You can name the file whatever
    you like but we strongly recommend you use the default name as it matches with
    the process that is running ::

        pidFile: /var/log/shotgunEventDaemon.pid

**eventIdFile**

    The eventIdFile points to the location where the daemon will store the id of the 
    last processed Shotgun event. This will allow the daemon to pick up where it left 
    off when it was last shutdown, thus it won't miss any events. If you want to 
    ignore any events since the last daemon shutdown, remove this file before
    starting up the daemon and the daemon will process only new events created after 
    startup. 

    This file keeps track of the last event id for *each* plugin and stores this
    information in picked format. ::

        eventIdFile: /var/log/shotgunEventDaemon.id

**logMode**

    The logging mode can be set to one of two values:

    - **0** = all log messages in the main log file
    - **1** = one main file for the engine, one file per plugin

    When using a value of **1**, the log messages generated by the engine itself
    will be logged to the main logfile specified by the ``logFile`` config setting.
    Any messages logged by a plugin will be placed in a file named 
    ``plugin.<plugin_name>``.
    ::

        logMode: 1

**logPath**

    The path where to put log files (both for the main engine and plugin log 
    files). The name of the main log file is controlled by the ``logFile`` 
    setting below. ::

        logPath: /var/log/shotgunEventDaemon

    .. note::

        The shotgunEventDaemon will have to have write permissions for this directory.
        In a typical setup, the daemon is set to run automatically when the machine
        starts up and is given root priveleges at that point.

**logFile**

    The name of the main daemon log file. Logging is configured to store up to 
    10 log files that rotate every night at midnight. ::

        logFile: shotgunEventDaemon

**logging**

    The threshold level for log messages sent to the log files. This value is the 
    default for the main dispatching engine and can be overriden on a per
    plugin basis. This value is simply passed to the Python logging module. The 
    most common values are:
    - **10** - Debug
    - **20** - Info
    - **30** - Warnings
    - **40** - Error
    - **50** - Critical

    ::

        logging: 20

**conn_retry_sleep**

    If the connection to Shotgun fails, number of seconds to wait until the 
    connection is re-attempted. This allows for occasional network hiccups, 
    server restarts, application maintenance, etc. ::

        conn_retry_sleep = 60

**max_conn_retries**

    Number of times to retry the connection before logging an error level message 
    (which potentially sends an email if email notification is configured below). 
    ::

        max_conn_retries = 5

**fetch_interval**

    Number of seconds to wait before requesting new events after each batch of 
    events is done processing. This setting generally doesn't need to be 
    adjusted. ::

        fetch_interval = 5

Shotgun Settings
----------------

The following are settings related to your Shotgun instance.

**server**

    The url for the Shotgun server to connect to. ::

        server: $SHOTGUN_URL$

    .. note:: 

        There is no default value here. You must replace the $SHOTGUN_URL$ token with 
        the url for your Shotgun server (ie. https://awesome.shotgunstudio.com)


**name**

    The Shotgun Script name the shotgunEventDaemon should connect with. ::

        name: $SHOTGUN_SCRIPT_NAME$

    .. note::
        
        There is no default value here. You must replace the $SHOTGUN_SCRIPT_NAME$ 
        token with the Script name for your Shotgun server (ie. ``shotgunEventDaemon``)


**key**

    The Shotgun Application Key for the Script name specified above. ::

        key: $SHOTGUN_API_KEY$

    .. note::
        
        There is no default value here. You must replace the $SHOTGUN_API_KEY$ 
        token with the Application Key for your Script name above (ie. 
        ``0123456789abcdef0123456789abcdef01234567``)



**use_session_uuid**

    Sets the session_uuid from every event in the Shotgun instance to propagate in
    any events generated by plugins. This will allow the Shotgun UI to display
    updates that occur as a result of a plugin. ::

        use_session_uuid: True

    .. note::

        - Shotgun server v2.3+ is required for this feature.
        - Shotgun API v3.0.5+ is required for this feature.

    .. note::

        The Shotgun UI will *only* show updates live for the browser session that 
        spawned the original event. Other browser windows with the same page open 
        will not see updates live.


Plugin Settings
---------------

**paths**

    A comma delimited list of complete paths where the framework should look for 
    plugins to load. Do not use relative paths. ::

        paths: $PLUGIN_PATHS$

    .. note::
        
        There is no default value here. You must replace the $PLUGIN_PATHS$ 
        token with the location(s) of your plugin files (ie. 
        ``/usr/local/shotgun/shotgunEvents/plugins``)



Email Settings
--------------

These are used for error reporting because we figured you wouldn't constantly be 
tailing the log and would rather have an active notification system.

Any error above level 40 (ERROR) will be reported via email if all of the settings
are provided below.

All of these values must be provided for there to be email alerts sent out.

.. warning::

    Currently the email functionality requires Python v2.6 or above.

**server**

    The server that should be used for SMTP connections. The username and password
    values can be uncommented to supply credentials for the SMTP connection. If 
    your server does not use authentication, you shoult comment out the settings 
    for ``username`` and ``password`` ::

        server: $SMTP_SERVER$

    .. note::
        
        There is no default value here. You must replace the $SMTP_SERVER$
        token with the address of your smtp server (ie. ``smtp.mystudio.com``). 



**username**

    If your SMTP server requires authentication, uncomment this line and replace the
    $SMTP_USERNAME$ token with the username required to connect to your SMTP server. ::

        username: $SMTP_USERNAME$

**password**

    If your SMTP server requires authentication, uncomment this line and replace the
    $SMTP_PASSWORD$ token with the password required to connect to your SMTP server. ::

        password: $SMTP_PASSWORD$

**from**

    The from address that should be used in emails. ::

        from: $FROM_EMAIL$

    .. note::
        
        There is no default value here. You must replace the $FROM_EMAIL$ token with
        a value (ie. ``noreply@mystudio.com``).


**to**

    A comma delimited list of email addresses to whom these alerts should be sent. ::

        to: $TO_EMAILS$

    .. note::
        
        There is no default value here. You must replace the $TO_EMAILS$ token with
        a value (ie. ``shotgun_admin@mystudio.com``).


**subject**

    An email subject prefix that can be used by mail clients to help sort out
    alerts sent by the Shotgun event framework. ::

        subject: [SG]


