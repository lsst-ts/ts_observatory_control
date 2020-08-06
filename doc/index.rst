.. py:currentmodule:: lsst.ts.observatory.control

.. _observatory-control:

###################
Observatory Control
###################

.. image:: https://img.shields.io/badge/GitHub-ts_observatory_control-green.svg
    :target: https://github.com/lsst-ts/ts_observatory_control
.. image:: https://img.shields.io/badge/Jenkins-ts_observatory_control-green.svg
    :target: https://tssw-ci.lsst.org/job/LSST_Telescope-and-Site/job/ts_observatory_control/
.. image:: https://img.shields.io/badge/Jira-ts_observatory_control-green.svg
    :target: https://jira.lsstcorp.org/issues/?jql=labels+%3D+ts_observatory_control

.. _overview:

Overview
========

The Vera Rubin Observatory control system is a highly distributed system composed of a myriad of independent components that must act together to perform high-level operations.
By high-level operations we mean actions such as commanding the telescope to slew to to a position in the sky, wait for the telescope, dome and all the other components to be ready and then perform observations.

Commanding and monitoring the state and other particular events from each individual component can be valuable when it comes to performing regular observations, commissioning and/or engineering activities but can be extremely taxing for users.
This collection of high-level control software is designed to help mitigate the issue.
The software is organized into a set of classes that bundle together functionality from a group of components, essentially grouping the coordinated action of many CSCs into single high-level operations.
Users can utilize these classes separately to control a set of components or combine them to achieve even higher levels of operations.

.. _user-documentation:

User Documentation
==================

User-level documentation, found at the link below, is aimed at observers and operators looking to perform interactive operations with any of the telescopes and/or their components.
In most cases, users use the observatory control package from a Jupyter notebook to execute tasks in a controlled and highly interactive environment.

.. toctree::
    user-guide/user-guide
    :maxdepth: 1

Information about how to connect to the Jupyter notebook server is available in the observatory control system `nublado interface documentation <https://obs-controls.lsst.io/index.html#nublado-jupyter-interface>`__.

Most of the tasks available in this package are encapsulated by a `SAL Script`_ that can be launched in the `ScriptQueue`_, which provides a less-interactive and more user friendly interface.
Information about operating the system using the `ScriptQueue`_ can be found in the observatory control system `user interfaces documentation <https://obs-controls.lsst.io/index.html#control-system-user-interfaces>`__.

.. _SAL Script: https://ts-salobj.lsst.io/sal_scripts.html
.. _ScriptQueue: https://ts-scriptqueue.lsst.io

.. _development-documentation:

Developer Documentation
=======================

This area of documentation focuses on the classes used, API's, and how to participate to the development of the [CSC] software packages.

.. toctree::
    developer-guide/developer-guide
    :maxdepth: 1

.. version-history:

Version History
===============

.. toctree::
    version_history
    :maxdepth: 1
