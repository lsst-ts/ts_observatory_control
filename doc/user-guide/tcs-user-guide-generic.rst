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
For instance, to slew the telescope to `azimuth=0` and `elevation=80` degrees;

.. code:: python

    await tcs.point_azel(az = 0, el=80)

By default the method will set the rotator physical angle to zero, thought it is also possible to set a desired angle as well (also in degrees).
In additional, it is also possible to set a name for the position.

.. code:: python

    await tcs.point_azel(az = 0, el=20, rot_tel=90, target_name="maintenance xyz")


It is possible to slew to an ``ICRS`` coordinate using :py:meth:`slew_icrs <lsst.ts.observatory.control.BaseTCS.slew_icrs>`.
It assumes ``ra`` is in hours and ``dec`` in degrees but it also accepts values in `astropy.units` and `astropy.Angle`.
For instance, all the commands bellow slew to the same target.
It is recommended, but not required, to set the target name.

.. code:: python

    #  coordinate in sexagesimal, separated by ":"
    #  bare-minimum command set
    await tcs.slew_icrs(ra="20:00:00.0", dec="-80:00:00.00")

    #  coordinate in sexagesimal, separated by space
    #  and setting object name
    await tcs.slew_icrs(
              ra="20 00 00.0", dec="-80 00 00.00", target_name="Test target"
          )

    #  coordinate in sexagesimal, separated by ":" in ra and space in dec
    await tcs.slew_icrs(
              ra="20:00:00.0", dec="-80 00 00.00", target_name="Test target"
          )

    #  coordinate in float
    await tcs.slew_icrs(
              ra=20.0, dec=-80.0, target_name="Test target"
          )

    # coordinate as astropy.units, passing RA in degrees
    from astropy import units as u

    await tcs.slew_icrs(
              ra=300.0 * u.deg, dec=-80.0, target_name="Test target"
          )

    # coordinate as astropy.Angle
    from astropy.coordinates import Angle

    await tcs.slew_icrs(
        ra=Angle(20, unit=u.hourangle),
        dec=Angle(-80, unit=u.deg),
        target_name="Test target"
    )

    # coordinate as astropy.Angle, passing RA in degrees
    from astropy.coordinates import Angle

    await tcs.slew_icrs(
        ra=Angle(300, unit=u.deg),
        dec=Angle(-80, unit=u.deg),
        target_name="Test target"
    )

It is important to highlight that all commands above assume "position angle" equal to zero.
Position angle is defined as the angle between the East-axis direction (as projected on the sky) and the instrument y-axis (see :numref:`fig-position-angle`).
In general, the instrument x-axis is defined as the readout (or serial-shift) direction and y-axis the parallel-shift direction.
With the advent of multiple-readout sections CCDs, defining the direction of the axis can be tricky.
In general, it is assumed that the upper part of the CCD serial and parallel readout happens in the positive x and y-directions respectively.
This is an often overlooked parameter when slewing to a target but it is also fundamental in determining the rotator/instrument orientation.

.. figure:: /_static/PositionAngle.png
   :name: fig-position-angle
   :target: ../_images/PositionAngle.png
   :alt: Position angle definition.

   Illustration of the definition of position angle.

Users can specify the position angle for the observation as well as use a couple different strategies for dealing with the rotator/instrument position.
This is controlled using a pair of parameters; ``rot`` and ``rot_type``, which allows the user to specify the desired value (in degrees) and rotator strategy, respectively.

The available strategies (and their meaning) are listed in :py:class:`RotType <lsst.ts.observatory.control.utils.RotType>`.
By default ``rot_type = RotType.SkyAuto``, which means ``rot`` is treated as "position angle" and that it can be adjusted to be in range, if necessary.
The adjustment consists of adding 180 degrees to the angle; this will usually, but not always, result in a rotation angle that is in range.
As with ``ra`` and ``dec``, ``rot`` can be specified as a float (assumed to be in degrees), as a sexagesimal string (separated by colon or space, also assumed to be in degrees), using astropy units or ``Angle``.

.. code:: python

    # Select position angle = 0. degrees, this is the default set and will
    # cause the North axis to be aligned with the y-axis of the image with East
    # in the negative direction of x-axis, e.g. North-up East-left
    # orientation.
    await tcs.slew_icrs(
              ra="20 00 00.0", dec="-80 00 00.00", rot=0, target_name="Test target"
      )

    # Select position angle = 90 degrees, this will cause the North axis to be
    # along the x-axis of the image and East will be pointing in the y-axis
    # direction, e.g. North-right East-up
    await tcs.slew_icrs(
              ra="20 00 00.0", dec="-80 00 00.00", rot=90, target_name="Test target"
          )

    # Select position angle = 90 degrees, passing as sexagesimal string with :
    await tcs.slew_icrs(
              ra="20 00 00.0", dec="-80 00 00.00", rot="90:00:00", target_name="Test target"
          )

    # Select position angle = 90 degrees, passing as sexagesimal string with spaces
    await tcs.slew_icrs(
              ra="20 00 00.0", dec="-80 00 00.00", rot="90 00 00", target_name="Test target"
          )

    # Select position angle = 90 degrees, using astropy units
    await tcs.slew_icrs(
              ra="20 00 00.0", dec="-80 00 00.00", rot=90*u.deg, target_name="Test target"
          )

    # Select position angle = 90 degrees, Using astropy Angle
    await tcs.slew_icrs(
              ra="20 00 00.0", dec="-80 00 00.00", rot=Angle(90, unit=u.deg), target_name="Test target"
          )

If you rather have the method not try to find a suitable angle in case the specified value is unreachable, specify ``rot_type=RotType.Sky``.

.. code:: python

    await tcs.slew_icrs(
              ra="20 00 00.0",
              dec="-80 00 00.00",
              rot=0,
              rot_type=RotType.Sky,
              target_name="Test target"
      )

Users also have the option to select a physical angle for the rotator.
For instance, if you are trying to keep the Rotator close to a particular physical range (due to some hardware limitation or observational strategy) and still want the rotator to track the sky, use ``rot_type=RotType.PhysicalSky`` instead;

.. code:: python

    # Use PhysicalSky rotator strategy with rot=20. This will cause the rotator
    # to start tracking at the rotator physical orientation of 20. degrees but
    # still track the sky.
    from lsst.ts.observatory.control.utils import RotType

    await tcs.slew_icrs(
              ra="20:00:00.0",
              dec="-80 00 00.00",
              rot=20,
              rot_type=RotType.PhysicalSky,
              target_name="Test target"
          )

This will cause the rotator to be positioned close to the physical (e.g. encoder) angle of ``20.`` degrees.
Note that this angle is defined at the start of the slew, and the telescope will resume tracking normally, so the rotator will be moving to de-rotate the field.

If instead, you need the rotator to remain fixed at a set position but the telescope must track (e.g. for filter changes on the main telescope), use the ``rot_type=RotType.Physical`` option.

.. code:: python

    # Use of Physical rotator strategy with rot=0 This will cause the
    # rotator to move to 0 degrees and not track.
    # WARNING: The telescope will track the alt/az axis but the rotator will
    # be kept fixed in physical position 0. degrees.
    await tcs.slew_icrs(
              ra="20:00:00.0",
              dec="-80 00 00.00",
              rot=0,
              rot_type=RotType.Physical,
              target_name="Test target"
          )

When conducting spectroscopy (e.g. with the Auxiliary Telescope) it is useful to be able to position the field in terms of the parallactic angle.
For that, one can use the ``rot_type=RotType.Parallactic`` parameter;

.. code:: python

    await tcs.slew_icrs(
              ra=20.0,
              dec=-80.0,
              rot=0,
              rot_type=RotType.Parallactic,
              target_name="Test target"
          )

Although the default ``rot=0`` is the most commonly used value when using ``rot_type=RotType.Parallactic``, the user is free to select any angle.

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

    await tcs.slew_object("M31", rot=45.)

    await tcs.slew_object("M31", rot=20, rot_type=RotType.PhysicalSky)

    await tcs.slew_object("M31", rot=0, rot_type=RotType.Physical)

    await tcs.slew_object("M31", rot=0, rot_type=RotType.Parallactic)
