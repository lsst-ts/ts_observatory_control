.. py:currentmodule:: lsst.ts.observatory.control

.. _lsst.ts.observatory.control:

###########################
lsst.ts.observatory.control
###########################

The Vera Rubing Observatory control system is a highly distributed system
composed of myriad of independent components that must act together to
perform high-level operations. By high-level operations we mean actions like
commanding the telescope to slewing to a position in the sky, wait for the
telescope, dome and all the other components to be ready and then perform
observations.

Commanding and sorting out the state of each individual component can be
valuable when it comes to performing commissioning and/or engineering
activities but can be extremely demanding for users. To help mitigate the
issue Telescope and Site provide this collection of high-level control
software. The software is organized into a set of classes than combine
functionality from a group of components. Users can use these classes
separately to control a set of components or combine them to achieve even
higher levels of operations.

For instance, the `ATCS` class combine functionality for all
"telescope-related" components of the Vera Rubin Auxiliary Telescope. Actions
like slewing the telescope, while making sure all involved components are in
`ENABLED` state and wait until all components are in position is as simple as;

::

   from lsst.ts.observatory.control import ATCS

   atcs = ATCS()

   await atcs.start_task

   await atcs.slew_object(name="Alf Pav")

A set of utilities are also provided that allow users to combine component
coordination with activities like data analysis and more.


The repo defines the `RemoteGroup` class which
represent a group of components in the control system. This class implements
basic functionality that is common to all groups of CSCs.

Usages: Limiting required resources
===================================

In some cases, the high level class may need to communicate with several
components at the same time to achieve high-level operations. Some of these
components can have high frequency topics which will make the remotes quite
heavy to operate. At the same time, depending on the number of remotes a group
defines, or the number of groups needed by a certain operation, the overall
resources might also be quite heavy. To work around this the `RemoteGroup` base
class provides ways for users to limit the resources to the minimum set
required for the intended usage. This is controlled by the optional parameter
`intended_usage` in `RemoteGroup`.

By default `intended_usage = None`, which causes the class to load all the
resources from the remotes. This can be very helpful when using Jupyter
notebooks or testing environments where the user need more flexibility.

The `Usages` class contains the usages definition. By default, only a small
subset of generic operations are defined, e.g., `All`, `StateTransition`,
`MonitorState` and `MonitorHeartBeat`. Note that the meaning of `Usages.All`
is to load the resources for all the defined operations and not to load all the
resources.

The resources needed for each operation are defined in the `usages` property of
the `RemoteGroup` class. This class property defines a dictionary where the
keys are the usages and the values are the resources. The resources are
instances of `types.SimpleNamespace` with attributes;

`components`
    List of components required for the usage. If a component is part of a
    group but it is not needed for a certain type of usage, the component will
    not be instantiated during the initialization procedure.

`readonly`
    Defines an operation as read only. This will cause all commands to be
    ignored.

`include`
    List with topics to include in the operation. The list is common to all
    components to avoid duplication of generic topics.

Users can combine usages in a bitwise operation, e.g.;

::

    intended_usage = Usages.StateTransition | Usages.MonitorHeartBeat

This would cause the class to load the combined resources for both
`StateTransition` and `MonitorHeartBeat` operations.

When subclassing `RemoteGroup`, users will probably also have to subclass the
`Usages` class to add operations define by their class, override the the
`usages` property to return a dictionary with the new definition and make sure
to return the new `Usages` class in `valid_use_cases`.


.. .. _lsst.ts.observatory.control-using:

.. Using lsst.ts.observatory.control
.. =================================

.. toctree linking to topics related to using the module's APIs.

.. .. toctree::
..    :maxdepth: 1

.. _lsst.ts.observatory.control-contributing:

Contributing
============

``lsst.ts.observatory.control`` is developed at https://github.com/lsst-ts/ts_observatory_control.
You can find Jira issues for this module under the `ts_observatory_control <https://jira.lsstcorp.org/issues/?jql=project%20%3D%20DM%20AND%20component%20%3D%20ts_observatory_control>`_ component.

.. If there are topics related to developing this module (rather than using it), link to this from a toctree placed here.

.. .. toctree::
..    :maxdepth: 1

.. .. _lsst.ts.observatory.control-scripts:

.. Script reference
.. ================

.. .. TODO: Add an item to this toctree for each script reference topic in the scripts subdirectory.

.. .. toctree::
..    :maxdepth: 1

.. .. _lsst.ts.observatory.control-pyapi:

Python API reference
====================

.. automodapi:: lsst.ts.observatory.control
   :no-main-docstr:
   :no-inheritance-diagram:

Revision History
================

.. toctree::
    version_history
    :maxdepth: 1
