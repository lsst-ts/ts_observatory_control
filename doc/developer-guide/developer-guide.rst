
.. _developer_guide:

###################################
Observatory Control Developer Guide
###################################

.. image:: https://img.shields.io/badge/GitHub-ts_observatory_control-green.svg
    :target: https://github.com/lsst-ts/ts_observatory_control
.. image:: https://img.shields.io/badge/Jenkins-ts_observatory_control-green.svg
    :target: https://tssw-ci.lsst.org/job/LSST_Telescope-and-Site/job/ts_observatory_control/
.. image:: https://img.shields.io/badge/Jira-ts_observatory_control-green.svg
    :target: https://jira.lsstcorp.org/issues/?jql=labels+%3D+ts_observatory_control

The repo defines the `RemoteGroup` class which represent a group of `Commandable SAL Components <https://obs-controls.lsst.io/System-Architecture/CSC-Overview/index.html>`__ (CSCs) in the control system.
This class implements basic functionality that is common to all groups of CSCs.

.. _usages:

Usages: Limiting required resources
===================================

In some cases, the high level class may need to communicate with several components at the same time to achieve high-level operations.
Some of these components can have high frequency topics which will make the remotes quite heavy to operate.
At the same time, depending on the number of remotes a group defines, or the number of groups needed by a certain operation, the overall resources might also be quite heavy.
To work around this the `RemoteGroup` base class provides ways for users to limit the resources to the minimum set required for the intended usage.
This is controlled by the optional parameter `intended_usage` in `RemoteGroup`.

By default `intended_usage = None`, which causes the class to load all the resources from the remotes.
This can be very helpful when using Jupyter notebooks or testing environments where the user need more flexibility.

The `Usages` class contains the usages definition.
By default, only a small subset of generic operations are defined, e.g., `All`, `StateTransition`, `MonitorState` and `MonitorHeartBeat`.
Note that the meaning of `Usages.All` is to load the resources for all the defined operations and not to load all the resources.

The resources needed for each operation are defined in the `usages` property of the `RemoteGroup` class.
This class property defines a dictionary where the keys are the usages and the values are the resources.
The resources are instances of `types.SimpleNamespace` with attributes;

`components`
    List of components required for the usage.
    If a component is part of a group but it is not needed for a certain type of usage, the component will not be instantiated during the initialization procedure.

`readonly`
    Defines an operation as read only.
    This will cause all commands to be ignored.

`include`
    List with topics to include in the operation.
    The list is common to all components to avoid duplication of generic topics.

Usages can be combined in bitwise operation, e.g.;

.. code:: python

    intended_usage = Usages.StateTransition | Usages.MonitorHeartBeat

This would cause the class to load the combined resources for both `StateTransition` and `MonitorHeartBeat` operations.

When subclassing `RemoteGroup`, users will probably also have to subclass the `Usages` class to add operations define by their class.
It will also be necessary to override the the `usages` property to return a dictionary with the new definition and make sure to return the new `Usages` class in `valid_use_cases`.

.. .. _lsst.ts.observatory.control-using:

.. Using lsst.ts.observatory.control
.. =================================

.. toctree linking to topics related to using the module's APIs.

.. .. toctree::
..    :maxdepth: 1

.. _contributing:

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

.. _api_ref:

Python API reference
====================

.. automodapi:: lsst.ts.observatory.control
   :no-main-docstr:
   :no-inheritance-diagram:

.. auxtel

.. automodapi:: lsst.ts.observatory.control.auxtel
   :no-main-docstr:
   :no-inheritance-diagram:

.. maintel

.. automodapi:: lsst.ts.observatory.control.maintel
   :no-main-docstr:
   :no-inheritance-diagram:
