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


Sharing state
-------------

If multiple callbacks need to share state many options may be used.

- Global variables. Ick. Please don't do this.
- An imported module that holds the state information. Ick, but a bit better
  than simple globals.
- A mutable passed in the *args* argument when calling
  :meth:`Registrar.registerCallback`. A state object of your design or something
  as simple as a dict. Preferred.
- Implement callbacks as __call__ on object instances and provide some shared
  state object at callback object initialization. Most powerful, most convoluted
  and might be a bit redundant vs. *args* argument method.
