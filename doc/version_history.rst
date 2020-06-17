.. py:currentmodule:: lsst.ts.observatory.control

.. _lsst.ts.observatory.control.version_history:

###############
Version History
###############

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
