"""
EXAMPLE: 

When a Task status is flipped to 'fin' (Final), lookup each downstream Task that is currently 
'wtg' (Waiting To Start) and see if all upstream Tasks are now 'fin'. If so, flip the downstream Task
to 'rdy' (Ready To Start)

You can modify the status values in the logic to match your workflow
"""

def registerCallbacks(reg):	
    """
    matchEvents is a dictionary where the key is the event_type (string) to match and the value is a list
    of attribute_names to match. In the example below, we will run this callback if the event_type is
    a 'Shotgun_Task_Change' and the attribute_name is 'sg_status_list' (ie. the status was changed on a 
    Task).
    
    You can also use '*' to match all values both in the key and in the value list. For example:
	# match all Shotgun_Task_Change events regardless of what attribute was modified.
	matchEvents = {
	    'Shotgun_Task_Change': ['*'],
	}
	or
	# match all events regardless of what event_type was generated (this processes every event... that's
	# a lot of them and probably not required unless you're doing something more advanced).
	matchEvents = {
	    '*': [],
	}
	
    """
	matchEvents = {
	    'Shotgun_Task_Change': ['sg_status_list'],
	}
	
	reg.registerCallback('$DEMO_SCRIPT_NAME$', '$DEMO_API_KEY$', flipDownstreamTasks, event_types, matchEvents, None)


def flipDownstreamTasks(sg, logger, event, args):
	"""Flip downstream Tasks to 'rdy' if all of their upstream Tasks are 'fin'"""
    
    # downtream tasks that are currently wtg
    ds_filters = [
        ['upstream_tasks', 'is', event['entity']],
        ['sg_status_list', 'is', 'wtg'],
        ]
    fields = ['upstream_tasks']

    for ds_task in sg.find("Task", ds_filters, fields):
        change_status = True

        # don't change status unless *all* upstream tasks are fin
        if len(ds_task["upstream_tasks"]) > 1:
            logger.debug("Task #%d has multiple upstream Tasks", event['entity']['id'])
            us_filters = [
                ['downstream_tasks', 'is', ds_task],
                ['sg_status_list', 'is_not', 'fin'],
                ]
            if len(sg.find("Task", filters)) > 0:
                change_status = False

        if change_status:
            sg.update("Task",ds_task['id'], data={'sg_status_list' : 'rdy'})
            logger.info("Set Task #%s to 'rdy'", ds_task['id'])
