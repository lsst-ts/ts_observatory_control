.. py:currentmodule:: lsst.ts.observatory.control

.. _lsst.ts.observatory.control.version_history:

###############
Version History
###############

v0.10.2
=======

* In `ATCS`:
  * Small fixes to find_target and object_list_get.
    Fix `ATCS.open_valve_instrument` to call `cmd_openInstrumentAirValve` instead of `cmd_m1OpenAirValve`.
    In `ATCS.usages`, add mainDoorState event to the list of required events on atdome.
    In `ATCS.open_m1_cover` use `open_valve_main` instead of `open_valves`. Only main valve needs to be open to open the m1 cover.
    In `ATCS.prepare_for_onsky`, stop enabling the components and add a check that all components are in enabled state.
    In `ATCS.prepare_for_flats`, add a step to verify that all components are in enabled state.
* In `RemoteGroup`:
  * Implement `assert_all_enabled` method to verify that all components in the group are in enabled state.
* In `ComCam`:
  * Implement `get_available_instrument_setup`.
* In `LATISS`:
  * Implement `get_available_instrument_setup`.
* In `BaseCamera`:
  * Add new abstract method `get_available_instrument_setup`.


v0.10.1
=======

* In ATCS update algorithm to open m1 cover.
* Add object storing and finding facility to BaseTCS.
* In ATCS add functionality to stop the monitor position loop.

v0.10.0
=======

* Refactor MTCS and ATCS unit tests to use ``DryTest`` mode (no remotes) and mock the expected behavior with ``unittest.mock``. This allows the unit tests to run much more quickly and reliable. The old unit tests relying on DDS will be converted to integration tests.
* Add support in ``RemoteGroup`` and ``BaseTCS`` to support setting up the class when there is no event loop running.
* In ``ATCS._slew``, pass in the internal ``check`` to ``monitor_position``.
* In ``MTCS``:
  * Add support for enabling/disabling CCW following mode.
  * Add check that ccw following mode is enabled when doing a slew activity.

v0.9.2
======

* Fix `absorb` option in offset_azel.
* Update how `BaseTCS._slew_to` handle `check`.
  This fixes an issue where calling `prepare_for_onsky` and `prepare_for_flatfield` would leave the users check attribute in a different state than that set by the user.
  This was also causing the `prepare_for_onsky` method to not open the dome.
* Fix checking that ATDomeTrajectory is in DISABLE while moving the dome.

v0.9.1
======

* Update emulators to publish data useful for INRIA.

v0.9.0
======

* Implement general purpose utility method in ``RemoteGroup`` to get components heartbeats and check liveliness of the group.
* Add ``enable_dome_following`` and ``disable_dome_following`` int ``BaseTCS`` to use new  ``ATDomeTrajectory`` ``setFollowingMode`` command.
  * Implement new enable/disable dome following in ``ATCS`` class.
* Set event specifying that dome is in position.
* Implement offset_x/offset_y functionality in slew commands so users can specify an offset from the original slew position.

v0.8.3
======

* Update close method in ``RemoteGroup`` to only close the domain if it was not given by the user.
* In ``ATCS.close_m1_cover``, flush ``m1CoverState`` before sending the command.
* Update ``MTCSUsages.All`` to include missing events/telemetry.

v0.8.2
======

* Add filter change (set/get) capability to ``ComCam`` class.
* Add offline function for ``RemoteGroup``.
* Fix/update docstring in ``BaseTCS.offset_xy`` and ``offset_azel``.
  Default value for relative parameter is `True` and docstring in offset_xy said it was `False`.


v0.8.1
======

* Update rotator strategies to use new pointing facility features.
  It is now possible to keep the rotator at a fixed orientation while tracking a target in az/el.
* Expose azimuth wrap strategy to the users.
* Add new `DryTest` usage to `MTCS` class that allows creating the class without any remote (useful for unit testing).
* Add Coordinate transformation functionality to `BaseTCS` class to allow transformation or Az/El to Ra/Dec and vice-versa.
  Add method to compute parallactic angle from ra/dec to `BaseTCS`.
* Rename `utils.parallactic_angle` method to `utils.calculate_parallactic_angle` and update docstring.
* Implement publish heartbeat loop in `BaseGroupMock`.
* Fix issue closing ATCSMock class.
  Using `asyncio.wait_for` is also causing some issues at close time. Replace it with a slightly dumber but more reliable procedure in `BaseGroupMock`.
* Add documentation about new coordinate transformation facility.

v0.8.0
======

Changes:

  * Add new feature to support synchronization between BaseTCS and BaseCamera.
  * Implement synchronization feature in ATCS.
  * Implement placeholder for synchronization feature in MTCS.

v0.7.6
======

Changes:

  * Reformat code using black 20.
  * Pin version of ts-conda-build to 0.3 in conda recipe.

v0.7.5
======

Changes:

  * Change default offset to ``relative=False``.
  * Deprecate use of ``persistent`` flag in offset commands.
  * Add new ``absorb`` flag to offset commands to replace ``persistent``.
  * Add unit tests for offset commands.
  * Replace usage of ``asynctest.TestCase`` with ``unittest.IsolatedAsyncioTestCase``.
  * Improve documentation on offset commands.

Requirements:

  * ts_salobj >= 5.6.0
  * ts_xml >= 7.1.0
  * ts_idl >= 2.0.0
  * IDL files for all components, e.g. built with ``make_idl_files.py``

v0.7.4
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

v0.7.3
======

Changes:

  * Updated plate scale to correct math error.
  * Modify latiss_constants.py to include a sweet-spot for the hologram.
    Also to make the plate-scale consistent.

Requirements:

  * ts_salobj >= 5.6.0
  * ts_xml >= 7.1.0
  * ts_idl >= 2.0.0
  * IDL files for all components, e.g. built with ``make_idl_files.py``

v0.7.2
======

Changes:

  * Update `docs/conf.py`.
  * Update version history.
  * Implement xml 7/8 compatibility.
  * Fix `add_point_data` in BaseTCS.
  * Fix timeout in opening/closing the dome.
  * Enable atspectrograph ATAOS correction in `ATCS.prepare_for_onsky`.

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
