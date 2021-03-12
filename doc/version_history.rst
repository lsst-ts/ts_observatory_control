.. py:currentmodule:: lsst.ts.observatory.control

.. _lsst.ts.observatory.control.version_history:

###############
Version History
###############

v0.7.1
======

Changes:

  * Add workaround to edge condition while homing the ATDome.
    Now if the dome is pressing the home switch and we send a home command, it will simply register the dome as homed and won't send any event to indicate the activity is complete.
  * Add method to reset all offsets in base_tcs.
  * Add set_rem_loglevel method in RemoteGroup, that allows users to set the log level for the remotes loggers.
  * Fix "restore check" feature in prepare for flats.
  * Fix direction of PhysicalSky rotator strategy.
  * Update ATCS to support specifying rotator park position and flat field position.
    When using point_azel to slew the telescope for a safe position, use the current nasmyth position.
  * Fix setting rotFrame in xml7/8 compatibility mode.
  * Update ronchi170lpmm sweet spot.
  * Support differential ra/dec tracking in BaseTCS.

Requirements:

  * ts_salobj >= 5.6.0
  * ts_xml >= 7.1.0
  * ts_idl >= 2.0.0
  * IDL files for all components, e.g. built with ``make_idl_files.py``

v0.7.1
======

Changes:

  * Implement xml 7/8 compatibility.
  * Fix `add_point_data` in BaseTCS.
  * Fix timeout in opening/closing the dome.
  * Add enable atspectrograph ATAOS correction in `ATCS.prepare_for_onsky`.

Requirements:

  * ts_salobj >= 5.6.0
  * ts_xml >= 7.1.0
  * ts_idl >= 2.0.0
  * IDL files for all components, e.g. built with ``make_idl_files.py``

v0.7.0
======

Changes:

* Implement workaround for issue with ATDome not reliably finishing open/close dome commands.
* Fix offset_done method in ATCS, to properly wait for offset to be completed.
* Improve handling of check.<component> in ATCS.shutdown.
* Add boresight xy-axis parity determination in ATCS.
* Implement xml 8 backward compatibility for MTMount in MTCS.
* Add scripts to run mocks from the command line.
* Add general base_tcs._offset method to manage offsets.
* Implement persistent offsets.

Requirements:

* ts_salobj >= 5.6.0
* ts_xml >= 7.1.0
* ts_idl >= 2.0.0
* IDL files for all components, e.g. built with ``make_idl_files.py``

v0.6.0
======

Changes:

* Implement changes required by xml 7.1:
  * Removes NewMTMount (replaced by MTMount)
  * Update MTMount topics names and attributes.
* Improve error messages when heartbeat monitor fails.
* Improve error messages when slew/track target commands fails.

Requirements:

* ts_salobj >= 5.6.0
* ts_xml >= 7.1.0
* ts_idl >= 2.0.0
* IDL files for all components, e.g. built with ``make_idl_files.py``


v0.5.1
======

Changes:

* Stop using topic ``application`` from ``MTRotator`` which is marked for deprecation.
* Remove git commit hooks and implement pre-commit.
* Implement Jenkins shared library for conda build.

Requirements:

* ts_salobj >= 5.6.0
* ts_xml >= 7.0.0
* ts_idl >= 2.0.0
* IDL files for all components, e.g. built with ``make_idl_files.py``

v0.5.0
======

Changes:

* Implement fixes required for xml 7.

Requirements:

* ts_salobj >= 5.6.0
* ts_xml >= 7.0.0
* ts_idl >= 2.0.0
* IDL files for all components, e.g. built with ``make_idl_files.py``

v0.4.2
======

Changes:

* Remove use of features marked for deprecation in salobj 6.
* Fix copyright messages that mentioned ts_standardscripts as the source package.
* Use ts-conda-build metapackage to build conda packages.

Requirements:

* ts_salobj >= 5.6.0
* ts_xml >= 6.1.0
* ts_idl >= 1.3.0
* IDL files for all components, e.g. built with ``make_idl_files.py``

v0.4.1
======

Changes:

* Move ``check_tracking`` to ``base_tcs``.
* Test ``check_tracking`` in ``test_mtcs``.

Requirements:

* ts_salobj >= 5.6.0
* ts_xml >= 6.1.0
* ts_idl >= 1.3.0
* IDL files for all components, e.g. built with ``make_idl_files.py``

v0.4.0
======

* Add ``UsagesResources`` class.
  The class provides a better interface for developers to encode use case information to control/reduce resources needed for operating with the control classes.
  Implement new ``UsagesResources`` class on existing classes: ``ATCS``, ``LATISS``, ``ComCam``, ``MTCS``.
* In ``RemoteGroup``, add ``components_attr``, which has a list of remotes names and make ``components`` return a list of CSC names.
  CSC names are the string used to create the Remotes (e.g., ``MTMount`` or ``Hexapod:1``) whereas remote names are the name of the CSC in lowercase, replacing the colon by and underscore (e.g., ``mtmount`` or ``hexapod_1``).

Requirements:

* ts_salobj >= 5.6.0
* ts_xml >= 6.1.0
* ts_idl >= 1.3.0
* IDL files for all components, e.g. built with ``make_idl_files.py``

v0.3.0
======

* Some minor changes to `RemoteGroup` to support components that only send out telemetry and events and do not reply to commands.
  This is to support the MTMount component.
* Add `BaseGroupMock` class.
  This class will make writing of mock classes with group of CSCs slightly easier, by taking care of a the basics.
* Add `BaseTCS` class to support generic `TCS` behavior.
* Add `BaseCamera` class to support generic `Camera` behavior.
* Modify `ATCS` and `LATISS` mock classes to use the BaseGroupMock.
* Initial implementation of `MTCS` with mock class and unit tests.
  Currently implemented the basics and a couple of slew commands.
* Some improvements on how resources isolation (using check namespace) is implemented in TCS classes.

Requirements:

* ts_salobj >= v5.6.0
* ts_xml >= v6.1.0
* ts_idl >= 1.2.2
* IDL files for all components, e.g. built with ``make_idl_files.py``

v0.2.2
======

Fix flake8 F541 violations.

Requirements:

* ts_salobj >=v5.6.0
* ts_xml >=5.1.0
* ts_idl >=v1.1.3
* IDL files for all components, e.g. built with ``make_idl_files.py``


v0.2.1
======

Update `ATCS` for compatibility with ts_salobj 5.13.
Use the ``set_start`` method of remote commands, where practical.
Fix a bug in `RemoteGroup.set_state`: ``settingsToApply`` could be `None` in calls to ``lsst.ts.salobj.set_summary_state``.

Requirements:

* ts_salobj >=v5.6.0
* ts_xml >=5.1.0
* ts_idl >=v1.1.3
* IDL files for all components, e.g. built with ``make_idl_files.py``

v0.2.0
======

Update package for compatibility with ts_xml 5.1.

Requirements:

* ts_salobj >=v5.6.0
* ts_xml >=5.1.0
* ts_idl >=v1.1.3
* IDL files for all components, e.g. built with ``make_idl_files.py``

v0.1.0
======

Classes moved out of ts_standardscripts into the new repository.
Implement new feature, `intended_usage`, to allow users to limit the resources
loaded at initialization time (useful for writing SAL Scripts).

Requirements:

* ts_salobj >=v5.6.0
* ts_idl >=v1.1.3
* IDL files for all components, e.g. built with ``make_idl_files.py``
