.. _SAL Script: https://ts-salobj.lsst.io/sal_scripts.html
.. _Remote: https://ts-salobj.lsst.io/py-api/lsst.ts.salobj.Remote.html#lsst.ts.salobj.Remote
.. _salobj.State: https://ts-salobj.lsst.io/py-api/lsst.ts.salobj.State.html#lsst.ts.salobj.State
.. _ScriptQueue: https://ts-scriptqueue.lsst.io
.. _salobj.BaseScript: https://ts-salobj.lsst.io/py-api/lsst.ts.salobj.BaseScript.html

.. _user-guide:

##############################
Observatory Control User Guide
##############################

.. image:: https://img.shields.io/badge/GitHub-ts_observatory_control-green.svg
    :target: https://github.com/lsst-ts/ts_observatory_control
.. image:: https://img.shields.io/badge/Jenkins-ts_observatory_control-green.svg
    :target: https://tssw-ci.lsst.org/job/LSST_Telescope-and-Site/job/ts_observatory_control/
.. image:: https://img.shields.io/badge/Jira-ts_observatory_control-green.svg
    :target: https://jira.lsstcorp.org/issues/?jql=labels+%3D+ts_observatory_control

The Observatory Control package provides users and developers with tools to interact with the Rubin Observatory System.
These tools are mainly Python classes/objects that represent major groups of components and encapsulate high-level operations involving those components.
Control classes are generally separated according to which telescope system is being commanded.

In many instances, such as the telescope control system, the Auxiliary and Main telescope control system classes contain a common code base.
Furthermore, there are aspects shared across all classes, such as identifying the required entities, or usages, for the given instantiation of a class.
For these reasons, prior to instantiating any of the individual classes it is imperative that any sections associated to common code bases be read and understood prior to using the specific class, starting with :ref:`user-guide-generic-class-functionality` and subsections therein.

If a common code documentation section exists for a certain class, it is referenced immediately at the top of the document.
The following are the classes, grouped according to their common base classes and associated telescope:

.. Can't get toctrees to do what I want here, so doing it manually.


**TCS Related Classes**

.. toctree::
   :maxdepth: 1

   tcs-user-guide-generic
   auxtel/atcs-user-guide
   maintel/mtcs-user-guide


**Main Telescope Related Classes**

.. toctree::
   :glob:

   maintel/*

**Auxiliary Telescope Related Classes**

.. toctree::
   :glob:

   auxtel/*


For an example of what these classes enable, the `ATCS` class combines functionality for all telescope-operation related components for the Vera Rubin Auxiliary Telescope.
Actions like slewing the telescope, while making sure all involved components are in `ENABLED` state and waiting until all components are in position is encapsulate in a single command;

.. code:: python

   from lsst.ts.observatory.control.auxtel import ATCS

   atcs = ATCS()

   await atcs.start_task

   await atcs.slew_object(name="Alf Pav")

More examples for this and other CSC groups are available in the :ref:`generic TCS user guide <user-guide-generic-telescope-control-operations>`.

In the following sections we provide some general guidance and insights in using these classes as well as a detailed description of the main operations available on each one of them.

.. _user-guide-generic-class-functionality:

##############################################
Generic Class Functionality and Initialization
##############################################

.. _user-guide-controlling-resources:

Controlling resources
=====================

When writing `SAL Script`_ and notebooks to perform high-level operations using many CSCs, one must be aware of resource consumption and allocation, as it may have substantial impact on the performance of the tasks.

Both SalObj and the high-level control modules provides simple ways to control these resources, that users can employ to improve their tasks.
There are mainly two features that can be used for this purpose; :ref:`user-guide-sharing-dds-domain` and :ref:`user-guide-limiting-resources`.

.. _user-guide-sharing-dds-domain:

Sharing DDS domain
------------------

When using multiple classes, for instance to control telescope and instrument, it is highly recommended to share some resources, which can reduce the overhead when running `SAL Script`_ and Jupyter notebooks.
The most common shareable resource is the DDS domain.
When running from a Jupyter notebook, this can done by creating a `salobj.Domain`_ and passing it to the classes:

.. _salobj.Domain: https://ts-salobj.lsst.io/py-api/lsst.ts.salobj.Domain.html#lsst.ts.salobj.Domain

.. code:: python

   from lsst.ts import salobj
   from lsst.ts.observatory.control.auxtel import ATCS, LATISS

   domain = salobj.Domain()

   atcs = ATCS(domain=domain)
   latiss = LATISS(domain=domain)

   await atcs.start_task
   await latiss.start_task

When writing a `SAL Script`_ for the `ScriptQueue`_ it is possible to use the scripts own domain.
In addition, it is also possible to pass the script log object so that logging from the class will also be published to SAL.

.. code:: python

   from lsst.ts import salobj
   from lsst.ts.observatory.control.auxtel.atcs import ATCS


   class MyScript(salobj.BaseScript):

     def __init__(self, index):

         super().__init__(index=index, descr="My script for some operation.")

         self.atcs = ATCS(domain=self.domain, log=self.log)

In the code above, note that ``self.log`` is not defined anywhere in the scope.
The reason is that ``MyScript`` inherits it from `salobj.BaseScript`_.
This is actually a custom `Python logging <https://docs.python.org/3/howto/logging-cookbook.html>`__ object that will publish log messages to DDS, allowing them to be stored in the EFD for debugging.

.. _user-guide-limiting-resources:

Limiting Resources
------------------

When writing a `SAL Script`_, it is very likely that only a small subset of topics (commands, events and telemetry) from a CSC group will be required.
For instance, a `SAL Script`_ that will enable all components on a group, will only require the components ``summaryState`` and ``settingVersions`` events and the state transition commands.
In this case, it is possible to save some time and resources by limiting the group class to subscribe only to the required set, instead of the full topics set.

The package allow users to do that through the ``intended_usage`` parameter.

By default ``intended_usage = None``, which causes the class to load all the resources from the remotes, which is useful when using the classes from Jupyter notebooks.

Each class defines a specific group of "usages", for different types of operations.
It is possible to combine usages, using bitwise operation, in case more than one operation is needed, e.g.;

.. code:: python

    intended_usage = Usages.StateTransition | Usages.MonitorHeartBeat

There is also a ``Usages.All`` option that should include the topics for all the supported operations (not to be confused with the ``intended_usage = None``, which loads all the topics from all the components in a group).

The feature is available when instantiating the class, for example;

.. code:: python

    from lsst.ts import salobj
    from lsst.ts.observatory.control.auxtel import ATCS, ATCSUsages


    class MyScript(salobj.BaseScript):

      def __init__(self, index):

          super().__init__(index=index, descr="My script for some operation.")

          self.atcs = ATCS(domain=self.domain, log=self.log, intended_usage=ATCSUsages.StateTransition)


Details of the available usages for each class is given furthermore.

.. _user-guide-generic-csc-group-behavior:

Generic CSC Group behavior
==========================

All CSC Group classes are constructed on top of the :py:class:`RemoteGroup <lsst.ts.observatory.control.RemoteGroup>` base class, which implement generic behavior for groups of CSCs.
These generic methods and attributes will (mostly) work equally regardless of the group class.

Probably the most commonly used generic operations are the :py:meth:`enable <lsst.ts.observatory.control.RemoteGroup.enable>` and :py:meth:`standby <lsst.ts.observatory.control.RemoteGroup.standby>` methods.

The idea is that, after running :py:meth:`enable <lsst.ts.observatory.control.RemoteGroup.enable>`, all CSCs in the group will be in the ``ENABLED`` state.
Components that where already in ``ENABLED`` state will be left in that state.
For components in any other state the method will make sure to send the required state transition commands to enable them.
The method can run without any input argument, though one must be aware that it need to know what setting to load when transition from ``STANDBY`` to ``DISABLED``.
If no input is given, the method will inspect the ``settingVersions`` event from the CSCs in the group and select the first item in ``settingVersions.recommendedSettingsLabels``.
It is possible to provide settings either partially of fully using the ``settings`` input parameter.

Following are a couple of examples of how to use the :py:meth:`enable <lsst.ts.observatory.control.RemoteGroup.enable>` method.

.. TODO: (DM-26261) Add/Document feature to inspect all settings from all components in a group.

This will inspect the ``settingVersions`` event from all CSCs in the `ATCS` group to determine the ``settingsToApply`` for each one of them.

.. code:: python

    from lsst.ts.observatory.control.auxtel import ATCS

    atcs = ATCS()

    await atcs.start_task

    await atcs.enable()

Override settings for ATAOS only.
Will inspect ``settingVersions`` event from all other CSCs in the group to determine the ``settingsToApply`` for the rest of them.

.. code:: python

    await atcs.enable(settings={"ataos": "constant_hex"})

And finally, override settings for all the CSCs in the group.
Note how some of them receive an empty string, which is a way of enabling the CSC with default settings (and also work for when the CSC is not configurable).

.. code:: python

    await atcs.enable(
        settings={
            "ataos": "current",
            "atmcs": "",
            "atptg": "",
            "atpneumatics": "",
            "athexapod": "current",
            "atdome": "test.yaml",
            "atdometrajectory": "",
        }
    )

To send ``all`` components to ``STANDBY`` state;

.. code:: python

    await atcs.standby()

It is also possible to perform state transition in individual CSCs or in subgroups using the :py:meth:`set_state <lsst.ts.observatory.control.RemoteGroup.set_state>` method.
To send the ``ATAOS`` into ``STANDBY`` state;

.. code:: python

    from lsst.ts import salobj
    from lsst.ts.observatory.control.auxtel import ATCS

    atcs = ATCS()

    await atcs.start_task

    await atcs.set_state(salobj.STANDBY, components=["ataos"])

To check what is the current state of a particular CSC in the group, one can use :py:meth:`get_state <lsst.ts.observatory.control.RemoteGroup.get_state>` method;

.. code:: python

    ataos_state = await atcs.get_state("ataos")
    print(ataos_state)

Note that the method returns a `salobj.State`_ object, which is easier to understand (``State.STANDBY`` is more informative than ``5``, which is what we get when using remotes to get the state from a CSC).

Another useful "generic" feature of the classes that users may rely on when working on Jupyter notebooks or when writing `SAL Script`_, is that they include a `Remote`_ for all its CSCs.
The remotes are included in a class attribute called ``rem``.
To access them simply do;

.. code:: python

    await atcs.rem.ataos.evt_heartbeat.next(flush=True, timeout=5)

The class also contains a list of the remote names, which is the name of the CSCs in lowercase.
If the component is indexed, the name will be appended with an underscore followed by the index, e.g.; the component ``Test`` with index 1 becomes ``test_1``.
A good way of knowing what CSCs are part of the group you are working with is to print this list;

.. code:: python

    print(atcs.components)

It is also possible to use this list to access the remotes programmatically, e.g.;

.. code:: python

    # Get one heartbeat and print the state of each component in ATCS
    for comp in atcs.components:
      await getattr(atcs.rem, comp).evt_heartbeat.next(flush=True, timeout=5)
      comp_state = await atcs.get_state(comp)
      print(f"{comp}: {comp_state!r}")



.. _user-guide-generic-camera-operations:

Generic Camera Operations
=========================

TBD
