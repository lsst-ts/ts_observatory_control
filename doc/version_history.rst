.. py:currentmodule:: lsst.ts.observatory.control

.. _lsst.ts.observatory.control.version_history:

###############
Version History
###############

v0.1.1
======

Update `ATCS` for compatibility with ts_salobj 5.13.
Use the ``set_start`` method of remote commands, where practical.
Fix a bug in `RemoteGroup.set_state`: ``settingsToApply`` could be `None` in calls to ``lsst.ts.salobj.set_summary_state``.

Requirements:

* ts_salobj >=v5.6.0
* ts_idl >=v1.3.0
* IDL files for all components, e.g. built with ``make_idl_files.py``

v0.1.0
======

Classes moved out of ts_standardscripts into the new repository.
Implement new feature, `intended_usage`, to allow users to limit the resources
loaded at initialization time (useful for writing SAL Scripts).

Requirements:

* ts_salobj >=v5.6.0
* ts_idl >=v1.3.0
* IDL files for all components, e.g. built with ``make_idl_files.py``
