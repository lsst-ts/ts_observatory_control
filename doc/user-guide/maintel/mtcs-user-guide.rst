
.. _user-guide-mtcs:

Main Telescope Control System (MTCS)
------------------------------------

.. _Dome: https://ts-dome.lsst.io/
.. _MTDomeTrajectory: https://ts-mtdometrajectory.lsst.io/
.. _MTMount: https://ts-mtmount.lsst.io/
.. _MTAOS: https://ts-mtaos.lsst.io/

.. warning::
    This page is under heavy development and is subject to change.

The :py:class:`MTCS <lsst.ts.observatory.control.maintel.MTCS>` class groups the components that are related to Main Telescope operations, such as slewing and tracking objects.
It is built on top of the :py:class:`BaseTCS <lsst.ts.observatory.control.BaseTCS>`.

The component CSCs that are part of this group are:

  * MTPtg
  * `MTMount`_
  * `MTAOS`_
  * `MTDomeTrajectory`_
  * `Dome`_
  * Hexapod
  * Rotator
  * MTM1M3
  * M2

