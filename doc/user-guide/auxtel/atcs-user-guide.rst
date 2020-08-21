.. _ATDome: https://ts-atdome.lsst.io
.. _ATDomeTrajectory: https://ts-atdometrajectory.lsst.io
.. _ATHexapod: https://ts-athexapod.lsst.io
.. _ATMCS: https://ts-atmcs.lsst.io>
.. _ATPneumatics: https://ts-atpneumatics.lsst.io>

.. _user-guide-atcs:

Auxiliary Telescope Control System (ATCS)
-----------------------------------------

The :py:class:`ATCS <lsst.ts.observatory.control.auxtel.ATCS>` class groups the components that are related to Auxiliary Telescope operations, such as slewing and tracking objects.
It is built on top of the :py:class:`BaseTCS <lsst.ts.observatory.control.BaseTCS>`.

The component CSCs that are part of this group are:

  * ATPtg
  * `ATMCS`_
  * ATAOS
  * `ATDomeTrajectory`_
  * `ATDome`_
  * `ATPneumatics`_
  * `ATHexapod`_

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
