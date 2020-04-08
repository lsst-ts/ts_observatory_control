######################
ts_observatory_control
######################

`Documentation <https://ts-observatory-control.lsst.io>`_

Observatory control software. The repo defines the `RemoteGroup` class which
represent a group of components () in the control system. This class implements
basic functionality that is common to all groups of CSCs. In addition,
this repository provides high-level control algorithm in the form of
specialized groups of CSCs, like ATCS, which implements high-level operation on
a specific group of CSCs.

Examples of high-level operation is to slew the telescope to a named target and
wait until all the principal components are in position (Telescope, Dome, etc).

This code is automatically formatted by black using a git pre-commit hook. To enable this:

Install the black Python package with

```
pip install black
```

Run git config core.hooksPath .githooks once in this repository.


.. Add a brief (few sentence) description of what this package provides.
