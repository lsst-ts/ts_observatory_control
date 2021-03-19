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

.. _user-guide-generic-telescope-control-operations-slewing-to-fixed-positions:

Slewing to fixed positions
--------------------------

To slew the telescope to an AzEl coordinate (for instance, to conduct some maintenance of calibration), it is possible to use :py:meth:`point_azel <lsst.ts.observatory.control.BaseTCS.point_azel>`.
The method will slew to a fixed position in the local coordinate and `will not` initiate tracking.
For instance, to slew the telescope to `azimuth=0` and `elevation=80` degrees;

.. code:: python

    await tcs.point_azel(az = 0, el=80)

By default the method will set the rotator physical angle to zero, thought it is also possible to set a desired angle as well (also in degrees).
In additional, it is also possible to set a name for the position.

.. code:: python

    await tcs.point_azel(az = 0, el=20, rot_tel=90, target_name="maintenance xyz")


.. _user-guide-generic-telescope-control-operations-slewing-and-tracking:

Slewing and tracking
--------------------

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

It is also possible to slew to a target by name using :py:meth:`slew_object <lsst.ts.observatory.control.BaseTCS.slew_object>`, as long as it can be resolved via `Simbad <http://simbad.u-strasbg.fr/simbad/sim-fid>`__.
The method is similar to :py:meth:`slew_icrs <lsst.ts.observatory.control.BaseTCS.slew_icrs>`, but receives the target name instead of the coordinates.

.. code:: python

    await tcs.slew_object("M31")

.. _user-guide-generic-telescope-control-operations-rotator-position-and-sky-position-angle:

Rotator position and Sky position angle
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

It is important to highlight that all commands above assume "position angle" equal to zero.
Position angle is defined as the angle between the East-axis direction (as projected on the sky) and the instrument y-axis (see :numref:`fig-position-angle`).
In general, the instrument x-axis is defined as the readout (or serial-shift) direction and y-axis the parallel-shift direction.

.. figure:: /_static/PositionAngle.png
   :name: fig-position-angle
   :target: ../_images/PositionAngle.png
   :alt: Position angle definition.

   Illustration of the definition of position angle.

With the advent of multiple-readout sections CCDs, defining the direction of the axis can be tricky.
In general, it is assumed that the upper part of the CCD serial and parallel readout happens in the positive x and y-directions respectively.

This is an often overlooked parameter when slewing to a target but it is also fundamental in determining the rotator/instrument orientation.

Users can specify the position angle for the observation as well as use a couple different strategies for dealing with the rotator/instrument position.
This is controlled using a pair of parameters; ``rot`` and ``rot_type``, which allows the user to specify the desired value (in degrees) and rotator strategy, respectively.

The available strategies (and their meaning) are listed in :py:class:`RotType <lsst.ts.observatory.control.utils.RotType>`.
By default ``rot_type = RotType.SkyAuto``, which means ``rot`` is treated as "position angle" and that it can be adjusted to be in range, if necessary.
The adjustment consists of adding 180 degrees to the angle; this will usually, but not always, result in a rotation angle that is in range.
As with ``ra`` and ``dec``, ``rot`` can be specified as a float (assumed to be in degrees), as a sexagesimal string (separated by colon or space, also assumed to be in degrees), using `astropy unit module`_ or `astropy Angle object`_.

.. _astropy unit module: https://docs.astropy.org/en/stable/units/
.. _astropy Angle object: https://docs.astropy.org/en/stable/api/astropy.coordinates.Angle.html

.. code:: python

    import astropy.units as u
    from astropy.coordinates import Angle

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

.. warning::

    When using ``rot_type=RotType.Physical`` the rotator will remain fixed and will NOT track the sky rotation.
    Long exposures taken while tracking with this strategy will show field rotation.

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

The same rotator options are available when using :py:meth:`slew_object <lsst.ts.observatory.control.BaseTCS.slew_object>`.

.. code:: python

    await tcs.slew_object("M31", rot=45.)

    await tcs.slew_object("M31", rot=20, rot_type=RotType.PhysicalSky)

    await tcs.slew_object("M31", rot=0, rot_type=RotType.Physical)

    await tcs.slew_object("M31", rot=0, rot_type=RotType.Parallactic)

.. _user-guide-generic-telescope-control-operations-offsetting:

Offsetting
----------

The pointing component (and thus the :py:class:`BaseTCS <lsst.ts.observatory.control.BaseTCS>` class) support several different offset options.

In terms of coordinate frames the following options are available:

  :py:meth:`offset_azel <lsst.ts.observatory.control.BaseTCS.offset_azel>`
    Offset telescope in azimuth and elevation.

  :py:meth:`offset_xy <lsst.ts.observatory.control.BaseTCS.offset_xy>`
    Offset telescope in terms of boresight.
    This will cause the field to move in x and y.

  :py:meth:`offset_radec <lsst.ts.observatory.control.BaseTCS.offset_radec>`
    Offset telescope in RA and Dec.
    Perform arc-length offset in sky coordinates.
    The magnitude of the offset is :math:`\sqrt{ra^2 + dec^2}` and the angle is the usual :math:`atan2(dec, ra)`.

The main distinction between the methods above is the coordinate frame they operate with.

Except for :py:meth:`offset_xy <lsst.ts.observatory.control.BaseTCS.offset_xy>` the resulting image offset will heavily depend on the position on the sky and the rotator configuration.
Therefore, when trying to position a start in a particular place of the FoV, it is highly recommended to use this method.

The :py:meth:`offset_xy <lsst.ts.observatory.control.BaseTCS.offset_xy>` method is designed to perform offset in image coordinates.
For instance;

.. code:: python

    await tcs.offset_xy(x=10., y=0.)

Will result in a 10. arcseconds offset **of the image** in the positive x direction.
The definition of x and y axis can be found in :numref:`user-guide-generic-telescope-control-operations-rotator-position-and-sky-position-angle` and :numref:`fig-position-angle`.
In :numref:`fig-offset-xy-example` we show an example of the result of using :py:meth:`offset_xy <lsst.ts.observatory.control.BaseTCS.offset_xy>`.

.. figure:: /_static/offset_xy_example.png
   :name: fig-offset-xy-example
   :target: ../_images/offset_xy_example.png
   :alt: offset xy example

   Illustration of :py:meth:`offset_xy <lsst.ts.observatory.control.BaseTCS.offset_xy>` method.

In addition to the different methods shown above, users also have control of how the offsets are treated by the pointing component.
For each command, there are two additional control flags the user can rely on to change the underlying behavior.

.. _user-guide-generic-telescope-control-operations-relative-vs-absolute-offsets:

Relative vs Absolute offsets
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This option is controlled by the ``relative`` input parameter of the offset methods.
By default offsets are absolute, e.g.; ``relative=False``.

Absolute offsets overrides any previous offset of the same time.
For instance, the following sequence of commands;

.. code:: python

    await tcs.offset_azel(az=10, el=0)
    await tcs.offset_azel(az=0, el=10)

Is equivalent to a 10 arcsec offset in elevation only;

.. code:: python

    await tcs.offset_azel(az=0, el=10)

The reason is that the second offset command will override the first command.

On the other hand, relative offsets will accumulate with one another, e.g.;

.. code:: python

    await tcs.offset_azel(az=10, el=0, relative=True)
    await tcs.offset_azel(az=0, el=10, relative=True)

Will result in an offset of 10 arcsec in azimuth **and** elevation.

Relative and absolute offsets can also be combined.
For instance, the following sequence of commands;

.. code:: python

    await tcs.offset_azel(az=10, el=0, relative=True)
    await tcs.offset_azel(az=0, el=10, relative=True)
    await tcs.offset_azel(az=0, el=10)

You will result in a 10 arcsec offset in azimuth and 20 arcsec in elevation; 10 arcsec from the relative offset and 10 from the absolute offset.

Furthermore, if, after doing the above, you now do;

.. code:: python

    await tcs.offset_azel(az=0, el=0)

It will reset the absolute offset to zero in both azimuth and elevation but will retain the 10 arcsec relative offsets in azimuth and elevation.

In all cases above, the offset will be overwritten if a new target is sent, e.g.;

.. code:: python

    await tcs.offset_azel(az=10, el=0, relative=True)
    await tcs.offset_azel(az=0, el=10, relative=True)
    await tcs.offset_azel(az=0, el=10)
    await tcs.slew_object("HD 164461")  # reset all offsets above

Will result in a slew with no offsets.

.. _user-guide-generic-telescope-control-operations-persistent-vs-non-persistent-offsets:

Persistent vs Non-Persistent offsets
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

It is possible to control whether offsets will persist between slews commands using the ``persistent`` flag.
By default offsets are non-persistent, e.g., ``persistent=False``.

Furthermore, the ``relative`` flag also applies to ``persistent`` offsets.

For example, the sequence of command bellow;

.. code:: python

    await tcs.offset_azel(az=10, el=0, relative=True, persistent=True)
    await tcs.offset_azel(az=0, el=10, relative=True, persistent=True)
    await tcs.offset_azel(az=0, el=10, persistent=True)
    await tcs.slew_object("HD 164461")

Will result in a slew offset by 10 arcsec in azimuth and 20 arcsec in elevation.

.. _user-guide-generic-telescope-control-operations-reseting-offsets:

Reseting offsets
^^^^^^^^^^^^^^^^

In order to reset offsets, users can rely on the :py:meth:`reset_offsets <lsst.ts.observatory.control.BaseTCS.offset_xy>` method.

.. code:: python

    await tcs.reset_offsets()

By default, the method will reset all offsets.

Users can control whether to reset only the persistent or the non-persistent offsets using the ``persistent`` and ``non_persistent``.
The relative and absolute offsets are always reseted for the selected option.

For example, the commands bellow show how to reset only the persistent and non-persistent offsets, respectively.

.. code:: python

    await tcs.reset_offsets(persistent=True, non_persistent=False)  # reset only persistent offsets
    await tcs.reset_offsets(persistent=False, non_persistent=True)  # reset only non-persistent offsets
