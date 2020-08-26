.. _user-guide-generic-telescope-control-operations:

Generic Telescope Control System (TCS) Operations
=================================================

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
The examples below are equally valid for the Main and Auxiliary telescopes.
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
