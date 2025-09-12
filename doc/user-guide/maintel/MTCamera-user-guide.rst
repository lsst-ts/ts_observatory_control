.. _user-guide-lsstcam:

LSST Camera (LSSTCam)
---------------------

.. warning::
    This page is under heavy development and is subject to change.

List of Observation Types for LSSTCam
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The observation types used when observing with `LSSTCam` (via the `IMGTYPE FITS` header) provide information to downstream users telling them the primary reason for the observation. It is preferable for observations that are being done for a specific purpose as part of standard observing to use a specific observation type to make it easy to find them and simplifies processing configurations. This metadata is available in Butler via the ``exposure.observation_type`` metadata field.

Here the list of all the agreed upon observation types.

.. list-table:: Observation types for LSSTCam
   :widths: 10 65
   :header-rows: 1

   * - Name
     - Purpose
   * - BIAS
     - A bias observation (shutter closed and 0s exposure).
   * - DARK
     - An exposure taken with the camera shutter closed.
   * - FLAT
     - Observation of the flatfield screen.
   * - OBJECT
     - A science observation suitable for standard survey processing.
       Called “science” in butler for consistency with other instruments.
   * - ENGTEST
     - Tracking observation of the sky (maybe with dome closed) used during
       telescope testing.
   * - ACQ
     - Short (~1s) exposure to check target acquisition or image quality after
       another observation (e.g., focus or CWFS sequence).
   * - CWFS
     - Curvature wavefront sensing images, typically extremely out of focus,
       used to determine wavefront errors and compute optical corrections.
   * - FOCUS
     - A sequence with a large initial focus offset. Data is taken while
       returning the focus toward its original position, passing it by a
       similar amount.
   * - STUTTERED
     - An observation where rows are shifted during the exposure.
   * - INDOME
     - An image taken in the dome with the shutter open but not aimed at the
       calibration screen or CBP.
   * - CBP
     - An image taken in the dome with the shutter open and pointed at the CBP.
   * - SFLAT
     - A sky or twilight flat.
   * - DFLAT
     - A flat-field exposure taken with lights off — effectively a dark with
       shutter open.
   * - SPOT
     - A spot observation.

