
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
For instance, the `ATCS` class combines functionality for all telescope-operation related components for the Vera Rubin Auxiliary Telescope.
Actions like slewing the telescope, while making sure all involved components are in `ENABLED` state and waiting until all components are in position is encapsulate in a single command;

.. code:: python

   from lsst.ts.observatory.control.auxtel import ATCS

   atcs = ATCS()

   await atcs.start_task

   await atcs.slew_object(name="Alf Pav")

More examples for this and other CSC groups are available :ref:`furthermore <user-guide-generic-telescope-control-operations>`.

In the following sections we provide some general guidance and insights in using these classes as well as a detailed description of the main operations available on each one of them.

.. _user-guide-controlling-resources:

Controlling resources
=====================

When writing `SAL Scripts`_ and notebooks to perform high-level operations using many CSCs, one must be aware of resource consumption and allocation, as it may have substantial impact on the performance of the tasks.

Both SalObj and the high-level control modules provides simple ways to control these resources, that users can employ to improve their tasks.
There are mainly two features that can be used for this purpose; :ref:`user-guide-sharing-dds-domain` and :ref:`user-guide-limiting-resources`.

.. _user-guide-sharing-dds-domain:

Sharing DDS domain
------------------

When using multiple classes, for instance to control telescope and instrument, it is highly recommended to share some resources, which can reduce the overhead when running `SAL Scripts`_ and Jupyter notebooks.
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


.. _user-guide-generic-telescope-control-operations:

Generic Telescope Control System Operations
===========================================

The same way groups of CSCs contains generic operations, a group of CSCs that is part of a Telescope Control System (TCS) group retain some common operations.
For instance, a TCS will be responsible for slewing the telescope and tracking a target on the sky.
The same way, a TCS will also be responsible for preparing the telescope for calibrations and on-sky operations.

To model these common TCS behavior the package implements :py:class:`BaseTCS <lsst.ts.observatory.control.BaseTCS>`.
This class itself is an `abstract class <https://docs.python.org/3/library/abc.html>`__ and cannot be used stand-alone, but is fully implemented by :py:class:`ATCS <lsst.ts.observatory.control.auxtel.ATCS>` and :py:class:`MTCS <lsst.ts.observatory.control.maintel.MTCS>`.
There are many advantages of this implementation as it minimizes code duplication and also provides users with a common interface and feature set, regardless of what telescope they are working with.

In terms of setting up and shutting down the system :py:class:`BaseTCS <lsst.ts.observatory.control.BaseTCS>` expands to add the following methods:

  * :py:meth:`prepare_for_flatfield <lsst.ts.observatory.control.BaseTCS.prepare_for_flatfield>`, to prepare the system for calibrations.
  * :py:meth:`prepare_for_onsky <lsst.ts.observatory.control.BaseTCS.prepare_for_onsky>`, to prepare the system for on-sky operations.
  * :py:meth:`shutdown <lsst.ts.observatory.control.BaseTCS.shutdown>` to stow the system.

The actual operation performed by each of those tasks is particular to the final implementation and is detailed in :ref:`user-guide-atcs` and :ref:`user-guide-mtcs`.

Furthermore, the TCS provides a suit of useful slew operations.
The examples bellow are equally valid for the Main and Auxiliary telescopes.
One would simply do:

.. code:: python

    from lsst.ts.observatory.control.auxtel import ATCS

    tcs = ATCS()

to operate the Auxiliary Telescope or;

.. code:: python

    from lsst.ts.observatory.control.maintel import MTCS

    tcs = MTCS()

for the Main Telescope.

To slew the telescope to an AzEl coordinate (for instance, to conduct some maintenance of calibration), it is possible to use :py:meth:`point_azel <lsst.ts.observatory.control.BaseTCS.point_azel>`.
The method will slew to a fixed position in the local coordinate and `will not` initiate tracking.
For instance, to slew the telescope to `azimuth=0.` and `elevation=80.` degrees;

.. code:: python

    await tcs.point_azel(az = 0., el=80.)

By default the method will set the rotator physical angle to zero, thought it is also possible to set a desired angle as well (also in degrees).
In additional, it is also possible to set a name for the position.

.. code:: python

    await tcs.point_azel(az = 0., el=20., rot_tel=90., target_name="maintenance xyz")


It is possible to slew to an ``ICRS`` coordinate using :py:meth:`slew_icrs <lsst.ts.observatory.control.BaseTCS.slew_icrs>`.
It assumes ``ra`` is in hours and ``dec`` in degrees but it also accepts values in `astropy.units` and `astropy.Angle`.
For instance, all the commands bellow slew to the same target.
It is recommended, but not required, to set the target name.

.. code:: python

    #  coordinate in sexagesimal, separated by ":"
    #  bare-minimum command set
    await tcs.slew_icrs(ra="20:00:00.0", dec="-80:00:00.00")

    #  coordinate in sexagesimal, separated by space
    #  setting object name and rot_sky angle
    await tcs.slew_icrs(
              ra="20 00 00.0", dec="-80 00 00.00", rot_sky=0., target_name="Test target"
          )

    #  coordinate in sexagesimal, separated by ":" in ra and space in dec
    await tcs.slew_icrs(
              ra="20:00:00.0", dec="-80 00 00.00", rot_sky=0., target_name="Test target"
          )

    #  coordinate in float
    await tcs.slew_icrs(
              ra=20.0, dec=-80.0, rot_sky=0., target_name="Test target"
          )

    # coordinate as astropy.units, passing RA in degrees
    from astropy import units as u

    await tcs.slew_icrs(
              ra=300.0 * u.deg, dec=-80.0, rot_sky=0.0, target_name="Test target"
          )

    # coordinate as astropy.Angle
    from astropy.coordinates import Angle

    await tcs.slew_icrs(
        ra=Angle(20., unit=u.hourangle),
        dec=Angle(-80., unit=u.deg),
        rot_sky=0.,
        target_name="Test target"
    )

    # coordinate as astropy.Angle, passing RA in degrees
    from astropy.coordinates import Angle

    await tcs.slew_icrs(
        ra=Angle(300., unit=u.deg),
        dec=Angle(-80., unit=u.deg),
        rot_sky=0.,
        target_name="Test target"
    )

The :py:meth:`slew_icrs <lsst.ts.observatory.control.BaseTCS.slew_icrs>` also implements a couple different rotator positioning strategies.
The most common strategy is to use ``rot_sky``, also known as position angle (PA), the angle between north direction and the bore-sight y-axis, measured in the eastward direction.
By default ``rot_sky=0.`` and it can be changed by passing in the desired value;

.. code:: python

    await tcs.slew_icrs(
              ra=20.0, dec=-80.0, rot_sky=90., target_name="Test target"
          )

Users also have the option to select a physical angle for the rotator.
For instance, if you are trying to keep the Rotator close to a particular physical range (due to some hardware limitation or observational strategy), use ``rot_phys_sky`` instead;

.. code:: python

    await tcs.slew_icrs(
              ra=20.0, dec=-80.0, rot_phys_sky=20., target_name="Test target"
          )

This will cause the rotator to be positioned close to the physical (e.g. encoder) angle of ``20.`` degrees.
Not that this angle is defined at the start of the slew, and the telescope will resume tracking normally, so the rotator will be moving to de-rotate the field.

If instead, you need the rotator to remain fixed at a set position but the telescope must track (e.g. for filter changes on the main telescope), use the ``rot_phys`` option.

.. code:: python

    # WARNING: The telescope will track the alt/az axis but the rotator will
    # be kept fixed in physical position 0. degrees.
    await tcs.slew_icrs(
              ra=20.0, dec=-80.0, rot_phys=0., target_name="Test target"
          )

When conducting spectroscopy (e.g. with the Auxiliary Telescope) it is useful to be able to position the field in terms of the parallactic angle.
For that, one can use the ``rot_par`` parameter;

.. code:: python

    await tcs.slew_icrs(
              ra=20.0, dec=-80.0, rot_par=0., target_name="Test target"
          )

Although ``rot_par=0.`` is the most commonly used value, the user is free to select any angle.

In case the user demands an angle outside the valid range, the task will fail and raise an exception and not slew to the demanded position.

  >>> await tcs.slew_icrs(...)
  ---------------------------------------------------------------------------
  AckError                                  Traceback (most recent call last)
  <ipython-input-25-be270f3a125b> in async-def-wrapper()
  .
  .
  .
  AckError: msg='Command failed', ackcmd=(ackcmd private_seqNum=1597989109,
  ack=<SalRetCode.CMD_FAILED: -302>, error=6611,
  result='Rejected : rotator position angle out of range')

The error message will show the exception traceback, which can be somewhat intimidating.
However, the important bit of information can be found in the last couple lines of the output (as shown above).
This is also valid in case the user tries to slew to any other unreachable position (e.g. zenith blind spot, low elevation, etc.).
In this case, the error message will vary accordingly.

It is also possible to slew to a target by name using :py:meth:`slew_object <lsst.ts.observatory.control.BaseTCS.slew_object>`, as long as it can be resolved via `Simbad <http://simbad.u-strasbg.fr/simbad/sim-fid>`__.
The method is similar to :py:meth:`slew_icrs <lsst.ts.observatory.control.BaseTCS.slew_icrs>`, but receives the target name instead of the coordinates.

.. code:: python

    await tcs.slew_object("M31")

    await tcs.slew_object("M31", rot_sky=45.)

    await tcs.slew_object("M31", rot_phys_sky=20.)

    await tcs.slew_object("M31", rot_phys=0.)

    await tcs.slew_object("M31", rot_par=0.)


.. _user-guide-generic-camera-operations:

Generic Camera Operations
=========================

TBD

.. _user-guide-auxiliary-telescope:

Auxiliary Telescope
===================

.. _user-guide-atcs:

Auxiliary Telescope Control System (ATCS)
-----------------------------------------

The :py:class:`ATCS <lsst.ts.observatory.control.auxtel.ATCS>` class groups the components that are related to telescope operations, such as slewing and tracking objects.
The components that are part of this group are:

  * ATPtg
  * ATMCS
  * ATAOS
  * ATDomeTrajectory
  * ATDome
  * ATPneumatics
  * ATHexapod

.. figure:: /_static/ATCS.png
   :name: fig-auxtel-architecture
   :target: ../_images/ATCS.png
   :alt: Auxiliary Telescope architecture

   A hierarchical commanding architecture of the ATCS components.
   The ``ATCS`` class provides an interface to operate this group of CSCs.

In addition, the package also provides the ancillary class :py:class:`ATCSUsages <lsst.ts.observatory.control.auxtel.ATCSUsages>`, which defines the available ``intended_usage``, as mentioned in :ref:`user-guide-limiting-resources`.

.. The :py:class:`ATCS <lsst.ts.observatory.control.auxtel.ATCS>` class provides some useful startup tasks that the user can rely on for setting up the system.

As shown in :ref:`user-guide-generic-csc-group-behavior` the :py:class:`ATCS <lsst.ts.observatory.control.auxtel.ATCS>` provides both the :py:meth:`enable <lsst.ts.observatory.control.RemoteGroup.enable>` and :py:meth:`standby <lsst.ts.observatory.control.RemoteGroup.standby>` methods to facilitate setting up and shutting down.
This can be used combined with the :py:attr:`ATCSUsages.StateTransition <lsst.ts.observatory.control.auxtel.ATCSUsages.StateTransition>` usage to limit resources as needed, e.g.;

.. code:: python

    from lsst.ts.observatory.control.auxtel import ATCS, ATCSUsages

    atcs = ATCS(intended_usage=ATCSUsages.StateTransition)

    await atcs.start_task

    # put all ATCS components in ENABLED state
    await atcs.enable()

    # put all ATCS components in STANDBY state
    await atcs.standby()

Furthermore, the :py:class:`ATCS <lsst.ts.observatory.control.auxtel.ATCS>` provides :py:meth:`prepare_for_flatfield <lsst.ts.observatory.control.auxtel.ATCS.prepare_for_flatfield>` method to prepare the system for calibrations, which can be used with :py:attr:`ATCSUsages.PrepareForFlatfield <lsst.ts.observatory.control.auxtel.ATCSUsages.PrepareForFlatfield>` (see :ref:`user-guide-generic-telescope-control-operations`).
This method will perform the following tasks subsequently;

  #.  Open the primary mirror cover. If the telescope is not in park position, it will make sure the elevation is above 70 degrees before opening the cover.
  #.  Put ``ATDomeTrajectory`` in ``DISABLED`` state, to prevent it from synchronizing the telescope and the dome.
  #.  Send telescope to flat-field position.
  #.  Send dome to flat-field position.
  #.  Put ``ATDomeTrajectory`` in ``ENABLED`` state.

Make sure the system is ``ENABLED`` before running the task;

.. code:: python

    from lsst.ts.observatory.control.auxtel import ATCS, ATCSUsages

    atcs = ATCS(intended_usage=ATCSUsages.PrepareForFlatfield)

    await atcs.start_task

    # put all ATCS components in ENABLED state
    await atcs.enable()

    # prepare ATCS for flat-field
    await atcs.prepare_for_flatfield()

To prepare the telescope for on-sky activities the class provides the task :py:meth:`prepare_for_onsky <lsst.ts.observatory.control.auxtel.ATCS.prepare_for_onsky>`, which can be used with :py:attr:`ATCSUsages.StartUp <lsst.ts.observatory.control.auxtel.ATCSUsages.StartUp>`.
This method will perform the following tasks subsequently;

  #.  Slew telescope to park position (in case telescope is in flat-field position or else).
  #.  If primary mirror cover is open (e.g. for calibrations), close it. This is to ensure the mirror is protected when we start opening the dome, to avoid dust and particles from following in it.
  #.  Move dome to oppose the setting Sun, to make sure no direct sunlight hits the inside of the dome and create thermal issues.
  #.  Open dome slit.
  #.  Once dome is open, open primary mirror cover and vent gates.
  #.  Enable ``ATAOS`` corrections.

In general, it is advised to make sure all components are in ``ENABLED`` state before running :py:meth:`prepare_for_onsky <lsst.ts.observatory.control.auxtel.ATCS.prepare_for_onsky>`, but the method also accepts a dictionary of ``settings`` and calls :py:meth:`enable <lsst.ts.observatory.control.RemoteGroup.enable>` at the beginning.

.. code:: python

    from lsst.ts.observatory.control.auxtel import ATCS, ATCSUsages

    atcs = ATCS(intended_usage=ATCSUsages.StartUp)

    await atcs.start_task

    # prepare ATCS for flat-field
    await atcs.prepare_for_onsky()

Following up on what was shown in :ref:`user-guide-generic-csc-group-behavior`, the following is also a valid way of running :py:meth:`prepare_for_onsky <lsst.ts.observatory.control.auxtel.ATCS.prepare_for_onsky>`.

Overriding the settings for a single component (e.g. ATAOS):

.. code:: python

    await atcs.prepare_for_onsky(settings={"ataos": "constant_hex"})

Or Overriding the settings for all components:

.. code:: python

    await atcs.prepare_for_onsky(
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

It is important to remember that, if the components are already enabled, they will be left in the ``ENABLED`` state and will not be re-cycled.
If you need to change the settings for a specific CSC, you will have to send it to ``STANDBY`` state first.
See :ref:`user-guide-generic-csc-group-behavior` for an example of how to use :py:meth:`set_state <lsst.ts.observatory.control.RemoteGroup.set_state>` to send individual CSCs in the group to ``STANDBY`` state.

All the slew methods discussed in :ref:`user-guide-generic-telescope-control-operations` are available in :py:class:`ATCS <lsst.ts.observatory.control.auxtel.ATCS>`, which can be used with :py:attr:`ATCSUsages.Slew <lsst.ts.observatory.control.auxtel.ATCSUsages.Slew>` to limit resource allocation, e.g.;

.. code:: python

    from lsst.ts.observatory.control.auxtel import ATCS, ATCSUsages

    atcs = ATCS(intended_usage=ATCSUsages.Slew)

    await atcs.start_task

    # Minimum set of parameters.
    await atcs.slew_icrs(ra="00 42 44.330", dec="+41 16 07.50")

    # Explicitly specify rot_sky and target_name (both optional).
    await atcs.slew_icrs(
              ra="00 42 44.330", dec="+41 16 07.50", rot_sky=0., target_name="M31"
          )

    # Minimum set of parameters.
    await atcs.slew_object("M31")

    # Explicitly specify rot_sky (optional).
    await atcs.slew_object("M31", rot_sky=0.)

For shutting down the observatory :py:meth:`shutdown <lsst.ts.observatory.control.BaseTCS.shutdown>`

.. _user-guide-latiss:

LSST Auxiliary Telescope Image and Slit less Spectrograph (LATISS)
------------------------------------------------------------------

TBD

.. _user-guide-atcalsys:

Auxiliary Telescope Calibration System (ATCalSys)
-------------------------------------------------

TBD

.. _user-guide-main-telescope:

Main Telescope
==============

TBD

.. _user-guide-mtcs:

Main Telescope Control System (MTCS)
------------------------------------

TBD

.. _user-guide-comcam:

Commissioning Camera (ComCam)
-----------------------------

TBD
