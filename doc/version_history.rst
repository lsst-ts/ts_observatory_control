.. py:currentmodule:: lsst.ts.observatory.control

.. _lsst.ts.observatory.control.version_history:

###############
Version History
###############

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
