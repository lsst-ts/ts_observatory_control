.. py:currentmodule:: lsst.ts.observatory.control

.. _lsst.ts.observatory.control.version_history:

===============
Version History
===============

.. towncrier release notes start

v0.43.0 (2025-08-25)
====================

New Features
------------

- Move MTAOS start/stop close loop logic to MTCS. (`DM-50762 <https://rubinobs.atlassian.net/browse/DM-50762>`_)
- Setup the electrometer after it is cycled. (`DM-51041 <https://rubinobs.atlassian.net/browse/DM-51041>`_)
- Added several different tests to mtcalsys.yaml: gain tests, monochromatic scans, ptc level tests and ptc daily sequences. (`DM-51094 <https://rubinobs.atlassian.net/browse/DM-51094>`_)
- Added ptc to the mtcalsys_schema to indicate if a test is a ptc. (`DM-51094 <https://rubinobs.atlassian.net/browse/DM-51094>`_)
- In slew_dome_to mtcs method, raise an error if mtdometrajectory is ignored and dome following is enabled. (`DM-51217 <https://rubinobs.atlassian.net/browse/DM-51217>`_)
- In ``mtcalsys.yaml``, add y band 940 LED config. (`DM-51217 <https://rubinobs.atlassian.net/browse/DM-51217>`_)
- In ``data/mtcalsys.yaml, update n_flat and reduce exp_times for whitelight_u band sequences. (`DM-51217 <https://rubinobs.atlassian.net/browse/DM-51217>`_)
- In ``data/mtcalsys.yaml``, update the exposure time for the ``whitelight_empty_M940L3`` and ``whitelight_y_10_M940L3`` calibrations sequences. (`DM-51217 <https://rubinobs.atlassian.net/browse/DM-51217>`_)
- `DM-51217 <https://rubinobs.atlassian.net/browse/DM-51217>`_
- In ``data/mtcalsys_schema.yaml``, remove calib_type, use_camera, and use_flatfield_electrometer from required parameters. (`DM-51217 <https://rubinobs.atlassian.net/browse/DM-51217>`_)
- In atcs.py, add feature to await that ataos m1 corrections are disabled before returning disable_ataos_corrections method. (`DM-51639 <https://rubinobs.atlassian.net/browse/DM-51639>`_)
- Added source tests with single LEDs (`DM-51802 <https://rubinobs.atlassian.net/browse/DM-51802>`_)
- Updated MTCalSys configuration. (`DM-51828 <https://rubinobs.atlassian.net/browse/DM-51828>`_)
- Updated MTCalSys configurations. (`DM-52162 <https://rubinobs.atlassian.net/browse/DM-52162>`_)
- Add guider roi selection task in ts_observatory_control (`OSW-77 <https://rubinobs.atlassian.net/browse/OSW-77>`_)
- Updated ``MTCS._wait_bump_test_ok`` to work when m1m3 actuator bump test runs concurrently. (`OSW-949 <https://rubinobs.atlassian.net/browse/OSW-949>`_)
- Added new ``MTCS.get_m1m3_actuator_to_test`` coroutine. This coroutine receives a list of actuators to test and will yield actuators to be tested in an order that allows them to run concurrently (`OSW-949 <https://rubinobs.atlassian.net/browse/OSW-949>`_)


Bug Fixes
---------

- In mtcs.py, fix issue handling command ack failure when opening the mirror covers and reduce elevation to open mirror to 20 deg. (`DM-51639 <https://rubinobs.atlassian.net/browse/DM-51639>`_)
- In MTCalsys.py, fix bugs in CBP methods. (`DM-51639 <https://rubinobs.atlassian.net/browse/DM-51639>`_)
- Added check for camera and m2 hexapods in position event in the ``MTCS.wait_for_inposition`` method. (`DM-51828 <https://rubinobs.atlassian.net/browse/DM-51828>`_)
- Updated the ``MTCS._slew`` method to pass in the local ``_check`` variable to the ``wait_for_inposition`` method. This should fix an issue with the ``point_azel`` method when ``wait_dome=False``. (`DM-51828 <https://rubinobs.atlassian.net/browse/DM-51828>`_)
- Updated MTCS._ready_to_take_data use wait_for_in_position instead of the custom implementation that was only taking into account the mount and the camera hexapod. (`DM-51828 <https://rubinobs.atlassian.net/browse/DM-51828>`_)
- Fixed MTCS.close_m1_cover reference to ack error. (`DM-51828 <https://rubinobs.atlassian.net/browse/DM-51828>`_)
- Fixed MTCS.open_m1_cover reference to ack error. (`DM-51828 <https://rubinobs.atlassian.net/browse/DM-51828>`_)
- Increased timeout for hard point test for m1m3 in MTCS. (`DM-51828 <https://rubinobs.atlassian.net/browse/DM-51828>`_)
- In ``test_dm_target_catalog.py`` replace incorrect units keyword with unit in Angle constructors and skip test if summit package not available. (`OSW-77 <https://rubinobs.atlassian.net/browse/OSW-77>`_)
- Fixed ``MTCS.stop_m1m3_bump_test``. The methos now receives no parameter and stops all running bump tests. (`OSW-949 <https://rubinobs.atlassian.net/browse/OSW-949>`_)
- Fixed an issue with ``MTCS._wait_bump_test_ok`` that would cause it to exit prematurely if it was running primary and secondary tests and the primary test failed. (`OSW-949 <https://rubinobs.atlassian.net/browse/OSW-949>`_)


Other Changes and Additions
---------------------------

- Minor updates to MTCalsys sequence configuration. (`DM-51428 <https://rubinobs.atlassian.net/browse/DM-51428>`_)
- In MTCalsys.yaml, update sequence configurations. (`DM-51639 <https://rubinobs.atlassian.net/browse/DM-51639>`_)


v0.42.0 (2025-06-06)
====================

New Features
------------

- Add CBP and CBP electrometers to MTCalsys. (`DM-47497 <https://rubinobs.atlassian.net/browse/DM-47497>`_)
- Add option to specify wavelengths with nonlinear spacing. (`DM-47497 <https://rubinobs.atlassian.net/browse/DM-47497>`_)
- Adding function to read out the location of all linear stages for the Calibration Projector in MTCalsys (`DM-49065 <https://rubinobs.atlassian.net/browse/DM-49065>`_)
- Add mechanism in the ``LSSTCam`` class to handle filter changes. (`DM-49278 <https://rubinobs.atlassian.net/browse/DM-49278>`_)
- Added a function to park the LED Projector. (`DM-49346 <https://rubinobs.atlassian.net/browse/DM-49346>`_)
- added homing to the setup_calsys and turned off LEDs in the prepare_for_flat (`DM-49346 <https://rubinobs.atlassian.net/browse/DM-49346>`_)
- Updated the indices for the linear stages and fibers spectrographs (`DM-49346 <https://rubinobs.atlassian.net/browse/DM-49346>`_)
- Add azMotion to Slew usages in ``MTCS`` class. (`DM-49414 <https://rubinobs.atlassian.net/browse/DM-49414>`_)
- In MTCS ``slew_dome_to`` method, increase timeout. (`DM-49414 <https://rubinobs.atlassian.net/browse/DM-49414>`_)
- Add open and close MTDome shutter door implementations in ``MTCS`` class. (`DM-49506 <https://rubinobs.atlassian.net/browse/DM-49506>`_)
- Updated the name of the LED in the i-band (`DM-49553 <https://rubinobs.atlassian.net/browse/DM-49553>`_)
- Updated the locations for the LED stages. (`DM-49553 <https://rubinobs.atlassian.net/browse/DM-49553>`_)
- In mtcalsys.py:
  - Add axis to linearstage cmd_getHome calls.
  - Replace start with set_start to getHome commands.
  - Set led_focus_axis and linearstage_axis to 0 instead of 1.
  - Add index 0 to position calls.
  - Added details to projector status info.
  - Reformat input str to turn_led_on.
  - Move calls to instatiate electrometer and fiberspec with no spectrographs.
  - Swapped spectrograph indices.
  - Add call to setup electrometer.
  - Switch idx for led and laser focus.
  - Updated _take_data method for case with no camera.
  - Update unit tests. (`DM-49954 <https://rubinobs.atlassian.net/browse/DM-49954>`_)
- In maintel/lsstcam.py:
  - Update LSSTCam to add imageInOODS event to TakeImage and TakeImageFull usages.
  - Add ccsCommandState event to the set of camera events to take image.
  - Update _setup_mtcs_for_filter_change to also stop the rotator after stop tracking.
  - Update _setup_mtcs_for_filter_change to only move the rotator if it is not close to zero.
  - Update unit tests. (`DM-49954 <https://rubinobs.atlassian.net/browse/DM-49954>`_)
- In maintel/mtcs.py:
  - Add new AOS usage to the MTCS class.
  - Update the m1m3_booster_valve async context manager to only clear the slew flag if the operation succeed.
  - Use new unreliable in position feature to handle rotator in position event.
  - Refactor dome shutter operations methods.
  - Add mtaos closedLoopState event to the slew usage.
  - Add controllerState to the list of events for the Slew usage.
  - Update unit tests to accommodate changes. (`DM-49954 <https://rubinobs.atlassian.net/browse/DM-49954>`_)
- In mtcalsys.yaml, update sequence names with LSSTCam filters names. (`DM-49954 <https://rubinobs.atlassian.net/browse/DM-49954>`_)
- In base_camera.py:
  - Revert commit to refactor how start/end integration works.
  - Handle ccs command state for the camera.
  - Only run initGuider if exposure is larger than zero.
  - Skip error in initGuider if the error indicates it is not configured as guider.
  - Add _roi_spec_json attribute.
  - Update unit tests to accommodate changes. (`DM-49954 <https://rubinobs.atlassian.net/browse/DM-49954>`_)
- Added dacValue = 1.0 for all LEDs in setup_calsys (`DM-50224 <https://rubinobs.atlassian.net/browse/DM-50224>`_)
- Updated mtcalsys.yaml with dac values and new exposure times based on experience (`DM-50282 <https://rubinobs.atlassian.net/browse/DM-50282>`_)
- Added adjustdacValue in setup_calsys and prepare_for_flats, pulling from the configuration file (`DM-50282 <https://rubinobs.atlassian.net/browse/DM-50282>`_)
- In `maintel/lsstcam.py`:
  - Replace a log warning with an exception to prevent filter change if not configured to manage the operation.
  - Adds an exception handling for a stop rotator command.
    This ensures that even if the rotator does not respond to the stop command, the `setup_filter` method will log a warning and continue execution.
  - Update LSSTCam to add a default ROI spec, which will be used in any take image if the user does not provide an override. (`DM-50398 <https://rubinobs.atlassian.net/browse/DM-50398>`_)
- In `base_camera.py`, add back an attribute for storing Region of Interest (ROI) specification.
  This attribute will hold the configuration for the region of interest, allowing for better management of camera settings. (`DM-50398 <https://rubinobs.atlassian.net/browse/DM-50398>`_)
- Collating a bunch of run branch commits. (`DM-50749 <https://rubinobs.atlassian.net/browse/DM-50749>`_)
- Added new ``wait_tracking_stopped`` method that is awaited after sending the ``stopTracking`` command to the pointing component in ``BaseTCS.stop_tracking``. (`DM-50794 <https://rubinobs.atlassian.net/browse/DM-50794>`_)
- Refactored ``MTCS.move_rotator`` to make it more resilient.
    
  The method will first wait for a heartbeat from the ``MTRotator`` before sending the move command.
  Then, after sending the move command, it will wait until the rotator reports as moving.
  If the rotator does not start to move it will try again.
  If it fails for a second time, then an exception is raised. (`DM-50794 <https://rubinobs.atlassian.net/browse/DM-50794>`_)
- Implement new ``MTCS.wait_tracking_stopped`` method that will wait for the elevation and azimuth axis of the telescope to report as stopped and for the rotator to report as stationary. (`DM-50794 <https://rubinobs.atlassian.net/browse/DM-50794>`_)
- Refactored the ``MTCS.stop_rotator`` method to extract the logic that waits for the rotator to be stationary into a separate method. (`DM-50794 <https://rubinobs.atlassian.net/browse/DM-50794>`_)
- Updated ``MTCS.wait_dor_rotator_inposition`` to handle a condition where the rotator reports as being in position while still beig far from the target position. (`DM-50986 <https://rubinobs.atlassian.net/browse/DM-50986>`_)
- In mtcalsys.yaml, Increase number of u band pulses for cbp_u_2nm config. (`DM-50986 <https://rubinobs.atlassian.net/browse/DM-50986>`_)
- Changed default values for electrometer integration time and range to be more precise for PTC curves. (`DM-51043 <https://rubinobs.atlassian.net/browse/DM-51043>`_)
- Added led focus locations for individual LEDs (`DM-51046 <https://rubinobs.atlassian.net/browse/DM-51046>`_)


Bug Fixes
---------

- * Fixed incompatibilities with SIMBAD response. (`DM-49566 <https://rubinobs.atlassian.net/browse/DM-49566>`_)
- In mtcs.py fix flush keyword typo in wait_for_dome_state method. (`DM-49683 <https://rubinobs.atlassian.net/browse/DM-49683>`_)
- Temporary fix for LED ON/OFF swap in LEDProjector until permanent fix is made (`DM-50204 <https://rubinobs.atlassian.net/browse/DM-50204>`_)
- Fixed the way serial numbers of LEDs are called by ledprojector. (`DM-50204 <https://rubinobs.atlassian.net/browse/DM-50204>`_)
- Changed LED rest position (`DM-50224 <https://rubinobs.atlassian.net/browse/DM-50224>`_)
- increased timeout for homing stages (`DM-50224 <https://rubinobs.atlassian.net/browse/DM-50224>`_)
- Had to add mtcamera_filter to mtcamera_filter (`DM-50224 <https://rubinobs.atlassian.net/browse/DM-50224>`_, `DM-50224 <https://rubinobs.atlassian.net/browse/DM-50224>`_)
- Added axis to every move command for LinearStages (`DM-50280 <https://rubinobs.atlassian.net/browse/DM-50280>`_)
- Added groupId to the Electrometer and FiberSpectrograph exposures (`DM-50396 <https://rubinobs.atlassian.net/browse/DM-50396>`_)
- Increased timeout for linearstage_led_select to getHome from 20 seconds to 60 seconds (stage_home_timeout.) (`DM-50809 <https://rubinobs.atlassian.net/browse/DM-50809>`_)
- In mtcalsys.py, fix typo in electrometer name. (`DM-50986 <https://rubinobs.atlassian.net/browse/DM-50986>`_)
- Changed the led focus location for y-band LED (`DM-51046 <https://rubinobs.atlassian.net/browse/DM-51046>`_)


API Removal or Deprecation
--------------------------

- Remove dependencies on ``lsst.ts.idl`` and use ``lsst.ts.xml`` instead. (`DM-50775 <https://rubinobs.atlassian.net/browse/DM-50775>`_)


Other Changes and Additions
---------------------------

- The bump test logic for both M1M3 and M2 has been updated to support detailed failure statuses (e.g., `FAILED_TIMEOUT`, `FAILED_TESTEDPOSITIVE_OVERSHOOT`, etc.) introduced in the updated XML enumeration.
  Backward compatibility with the previous single `FAILED` logic has been preserved to ensure seamless integration. (`DM-49547 <https://rubinobs.atlassian.net/browse/DM-49547>`_)


v0.41.1 (2025-03-17)
====================

New Features
------------

- Added sequences in mtcalsys.yaml for the white light source tests, which won't use the camera (`DM-49257 <https://rubinobs.atlassian.net/browse/DM-49257>`_)


Bug Fixes
---------

- Updated the `find_target_simbad` method in `base_tcs.py` to comply with Simbad queries in astroquery version 0.4.8, following the recent update of astroquery and Simbad API. (`DM-48561 <https://rubinobs.atlassian.net/browse/DM-48561>`_)


Other Changes and Additions
---------------------------

- Replaced the `Jenkins` pipeline configuration with a simplified call to the shared library. (`DM-48561 <https://rubinobs.atlassian.net/browse/DM-48561>`_)


v0.41.0 (2025-02-24)
====================

New Features
------------

- Refactor take image operation to allow returning from a take image sequence as soon as the exposure finished, instead of having to wait for the endReadout event. (`DM-47552 <https://rubinobs.atlassian.net/browse/DM-47552>`_)
- Add support to ``RemoteGroup`` for disabling checks for a list of components. (`DM-47619 <https://rubinobs.atlassian.net/browse/DM-47619>`_)
- In maintel/mtcs.py, remove settling time after clearing slew flag (currently refered to as close booster valve in the code). (`DM-47890 <https://rubinobs.atlassian.net/browse/DM-47890>`_)
- In maintel/mtcs.py, add a context manager to ensure m1m3 is in engineering mode before/after some operation and add unit tests. (`DM-47890 <https://rubinobs.atlassian.net/browse/DM-47890>`_)
- Updated ``BaseTCS`` to introduce a mechanism to execute code to prepare the telescope for offsetting.

  This consist of having an async context manager that is used when calling the offset command.
  By default this context manager does nothing. (`DM-48023 <https://rubinobs.atlassian.net/browse/DM-48023>`_)
- Updated ``MTCS`` to implement ``ready_to_offset``, which uses the ``m1m3_booster_valve`` context manager to enable/disable slew flag before/after offseting. (`DM-48023 <https://rubinobs.atlassian.net/browse/DM-48023>`_)


API Removal or Deprecation
--------------------------

- In base_camera.py, remove support for splitting guider ROI specs into multiple part. Size limit no longer exists. (`DM-47414 <https://rubinobs.atlassian.net/browse/DM-47414>`_)


v0.40.0 (2024-12-03)
====================

New Features
------------

- Add method in ``ATCS`` to check if ATAOS corrections are enabled (`DM-38823 <https://rubinobs.atlassian.net/browse/DM-38823>`_)
- Adds initial implementation of MTCalsys. (`DM-43628 <https://rubinobs.atlassian.net/browse/DM-43628>`_)
- Add configuration schema validation support to ``BaseCalsys`` and schema validation files for ``ATCalsys`` and ``MTCalsys`` classes. (`DM-45260 <https://rubinobs.atlassian.net/browse/DM-45260>`_)
- Add description fields to ``ATCalsys`` and ``MTCalsys`` schema validation files. (`DM-45261 <https://rubinobs.atlassian.net/browse/DM-45261>`_)
- Implement dome parking in MTCS. (`DM-45609 <https://rubinobs.atlassian.net/browse/DM-45609>`_)
- Implement dome unpark in MTCS. (`DM-45610 <https://rubinobs.atlassian.net/browse/DM-45610>`_)
- In atcalsys, pass group_id metadata to the electromer and fiber spectrograph when taking data. (`DM-45696 <https://rubinobs.atlassian.net/browse/DM-45696>`_)
- In base_tcs.py, expand captured rotator limit exceptions during slew cmd. (`DM-45696 <https://rubinobs.atlassian.net/browse/DM-45696>`_)
- Add ``slew_dome_to`` method for main telescope in ``MTCS``. (`DM-45821 <https://rubinobs.atlassian.net/browse/DM-45821>`_)
- Increase minimum electrometer exposure time to 1 second for Keithley electrometer (`DM-46003 <https://rubinobs.atlassian.net/browse/DM-46003>`_)
- In atcalsys, remove work around to Electrometer going to Fault. (`DM-46011 <https://rubinobs.atlassian.net/browse/DM-46011>`_)
- In atcalsys, add index to group id. (`DM-46011 <https://rubinobs.atlassian.net/browse/DM-46011>`_)
- Extend TCS readiness check to other image types beyond OBJECT, such as:
  ENGTEST, CWFS and ACQ. (`DM-46179 <https://rubinobs.atlassian.net/browse/DM-46179>`_)
- In ``mtcalsys.yaml``, Added laser configuration information to all tests, including laser mode and optical configuration. (`DM-46276 <https://rubinobs.atlassian.net/browse/DM-46276>`_)
- Add features to allow ``MTCalSys`` to better handle the laser
  - In ``mtcalsys.py`` made the following changes: 
   - Added ``laser_start_propagate`` and ``laser_stop_propagate()``
   - Added ``get_laser_parameters()``
   - Improved ``setup_laser()`` to change the wavelength and the optical configuration
   - Changed ``change_laser_wavelength()`` so it can be used for the laser or whitelight system 
  - In ``mtcalsys.yaml`` added a laser functional setup
  - In ``mtcalsys_schema.yaml`` added laser mode and optical configuration (`DM-46276 <https://rubinobs.atlassian.net/browse/DM-46276>`_)
- Implement open and close mirror covers methods in MTCS. (`DM-46309 <https://rubinobs.atlassian.net/browse/DM-46309>`_)
- Add feature to allow ``ATCalSys`` to skip monochromator configuration. 

  - In ``atcalsys_schema.yaml``, add default values for wavelength, entrace_slit and exit_slit. 
    Add option to set monochromator_grating to None to skip monchromator configuration and set None as default value.
  - In ``atcalsys.py``, add feature to skip configuring monochromator if monchromator_grating is None.
  - In ``atcalsys.yaml``, update monochromator configuration values for ptc curves to skip monchromator configuration. (`DM-46458 <https://rubinobs.atlassian.net/browse/DM-46458>`_)
- In maintel/mtcs.py, update close_mirror_covers to stop tracking before closing the covers. (`DM-46978 <https://rubinobs.atlassian.net/browse/DM-46978>`_)
- Remove sign flips and arcsec conversion from offset_hexapod functions. (`DM-46978 <https://rubinobs.atlassian.net/browse/DM-46978>`_)
- Fix MTCS offset_m2_hexapod decentering signs. (`DM-46978 <https://rubinobs.atlassian.net/browse/DM-46978>`_)
- In maintel/mtcs.py, update flush_offset_events and offset_done method to take rotator into account. (`DM-46978 <https://rubinobs.atlassian.net/browse/DM-46978>`_)
- In maintel/comcam.py avoid filter change if filter is in place. (`DM-46978 <https://rubinobs.atlassian.net/browse/DM-46978>`_)
- In maintel/mtcs.py, update offset_m2_hexapod to use MTAOS offsetDOF to offset the m2 hexapod. (`DM-46978 <https://rubinobs.atlassian.net/browse/DM-46978>`_)
- In maintel/mtcs.py, update offset_camera_hexapod to use MTAOS offsetDOF to offset the camera hexapod. (`DM-46978 <https://rubinobs.atlassian.net/browse/DM-46978>`_)
- Add methods in ``MTCS`` to park and unpark the TMA. (`DM-46979 <https://rubinobs.atlassian.net/browse/DM-46979>`_)
- Implement dome homing in ``MTCS``. (`DM-46980 <https://rubinobs.atlassian.net/browse/DM-46980>`_)
- Cleanup of ``MTCalsys`` configuration file ``mtcalsys.yaml`` by removing attributes that use default values. (`DM-46983 <https://rubinobs.atlassian.net/browse/DM-46983>`_)
- Add new default values for ``ATCalsys`` configurations in ``atcalsys_schema.yaml``. (`DM-46983 <https://rubinobs.atlassian.net/browse/DM-46983>`_)
- Cleanup of ``ATCalsys`` configuration file ``atcalsys.yaml`` by removing attributes that use default values. (`DM-46983 <https://rubinobs.atlassian.net/browse/DM-46983>`_)
- Add new default values for ``MTCalsys`` configurations in ``mtcalsys_schema.yaml``. (`DM-46983 <https://rubinobs.atlassian.net/browse/DM-46983>`_)
- Update ``_wait_hard_point_test_ok`` method in ``MTCS`` to be compatible with concurrent executions. (`DM-47223 <https://rubinobs.atlassian.net/browse/DM-47223>`_)
- In ``maintel/comcam.py``, add CCOOD.evt_imageInOODS to TakeImage usage. (`DM-47381 <https://rubinobs.atlassian.net/browse/DM-47381>`_)
- Add the following to MTCSUsages.All:
  - mirrorCoversMotionState
  - compensationMode
  - m1m3 events
  - mirrorCoversSystemState
  - mirrorCoversLocksMotionState (`DM-47381 <https://rubinobs.atlassian.net/browse/DM-47381>`_)
- Implement simple TCS synchronization in MTCS. (`DM-47381 <https://rubinobs.atlassian.net/browse/DM-47381>`_)
- In ``maintel/mtcs.py``, create a local copy of the check attribute in the _slew method. (`DM-47381 <https://rubinobs.atlassian.net/browse/DM-47381>`_)
- In ``maintel/mtcs.py``, make the following updates the open_m1_cover and close_m1_cover methods:
  - Refactor open_m1_cover.
  - Refactor close_m1_cover.
  - Add stop_tracking later in the close_m1_cover operation. 
  - Add stop_tracking to the slew_to_m1_cover_operational_range method after pointing the telescope.
  - Update open_m1_cover to stop tracking if not repositioning the telescope. (`DM-47381 <https://rubinobs.atlassian.net/browse/DM-47381>`_)
- In ``maintel/mtcs.py``, increase m1m3 settling time. (`DM-47381 <https://rubinobs.atlassian.net/browse/DM-47381>`_)
- IN ``base_camera.py``, remove ROI spec splitting. (`DM-47381 <https://rubinobs.atlassian.net/browse/DM-47381>`_)
- In maintel/mtcs, update _handle_m1m3_hardpoint_correction_command to wait for m1m3_settle_time after enabling/disabling force balance. (`DM-47641 <https://rubinobs.atlassian.net/browse/DM-47641>`_)
- In maintel/mtcs.py, update wait_for_rotator_inposition to use a lower race condition timeout and to not await any settling time. (`DM-47641 <https://rubinobs.atlassian.net/browse/DM-47641>`_)
- In maintel/mtcs, use the custom race_condition_timeout for checking the mount and hexapod are in position. (`DM-47641 <https://rubinobs.atlassian.net/browse/DM-47641>`_)
- In base_tcs, update _handle_in_position method to expose the timeout to use when handling the initial state race condition.	81efa99	Tiago Ribeiro <tribeiro@lsst.org>	Dec 1, 2024 at 10:59 PM (`DM-47641 <https://rubinobs.atlassian.net/browse/DM-47641>`_)
- In maintel/mtcs, reduce m1m3 setting time. (`DM-47641 <https://rubinobs.atlassian.net/browse/DM-47641>`_)


Bug Fixes
---------

- Changed grating from Blue to Mirror for PTC curves to align with updated hardware configuration and xml (`DM-45975 <https://rubinobs.atlassian.net/browse/DM-45975>`_)
- In atcalsys, fix exposure time in PTC 3 (`DM-46011 <https://rubinobs.atlassian.net/browse/DM-46011>`_)
- Fix MTRotator enumeration from INITIALIZING to STATIONARY (`DM-46179 <https://rubinobs.atlassian.net/browse/DM-46179>`_)
- In atcalsys, fix group_id metadata, removing spaces. (`DM-46201 <https://rubinobs.atlassian.net/browse/DM-46201>`_)
- In ``BaseCalsys.load_calibration_config_file``, fix schema validation to update configurations with default values applied by ``salobj.DefaultingValidator``. (`DM-46983 <https://rubinobs.atlassian.net/browse/DM-46983>`_)
- In ``maintel/mtcs.py``, fix set_azel_slew_checks to take into account value of the check flag for mtdome and mtdometrajectory. (`DM-47381 <https://rubinobs.atlassian.net/browse/DM-47381>`_)


API Removal or Deprecation
--------------------------

- In MTCSAsyncMock remove old idl.enums import in favor of new xml.enums (`DM-46179 <https://rubinobs.atlassian.net/browse/DM-46179>`_)
- Removed backwards compatibility with m1m3 FATables not being in ts-xml. (`DM-47641 <https://rubinobs.atlassian.net/browse/DM-47641>`_)


Other Changes and Additions
---------------------------

- Temporary addition of Tunable Laser Optical Configuration into enum while xml prepared for deployment (`DM-46167 <https://rubinobs.atlassian.net/browse/DM-46167>`_)
- Improve error reporting in ``ATCalsys.prepare_for_flat``. (`DM-46477 <https://rubinobs.atlassian.net/browse/DM-46477>`_)


v0.38.1 (2024-08-16)
====================

New Features
------------

- Add logging to init_guider. (`DM-45467 <https://rubinobs.atlassian.net/browse/DM-45467>`_)


Bug Fixes
---------

- Change the exception raised by ``MTCS.run_m2_actuator_bump_test`` to ``RuntimeError`` and update the corresponding unit test. (`DM-41601 <https://rubinobs.atlassian.net/browse/DM-41601>`_)
- In base_camera, fix how roiSpec is constructed in init_guider and fix unit test. (`DM-45467 <https://rubinobs.atlassian.net/browse/DM-45467>`_)
- In ATCalySys, swap RED to BLUE filter for atmonochromator (for white light) and update configuration for ptc-1. (`DM-45467 <https://rubinobs.atlassian.net/browse/DM-45467>`_)


v0.38.0 (2024-07-30)
====================

New Features
------------

- Add support for initializing guiders to BaseCamera. (`DM-39830 <https://rubinobs.atlassian.net/browse/DM-39830>`_)
- Added in optimized exposure times calculations for the electrometer and fiberspectrograph. This required some changes to the configuration file. (`DM-44361 <https://rubinobs.atlassian.net/browse/DM-44361>`_)


Bug Fixes
---------

- Add use_electrometer and use_fiberspectrograph to the ptc atcalsys configurations. (`DM-45232 <https://rubinobs.atlassian.net/browse/DM-45232>`_)
- In atcalsys, fix how ATCalsysExposure is created in calculate_optimized_exposure_times.

  Make sure it explicitly passes the parameters by name to make sure they have the correct values. (`DM-45232 <https://rubinobs.atlassian.net/browse/DM-45232>`_)


v0.37.0 (2024-07-15)
====================

New Features
------------

- In ``auxtel/atcs.py``, add new routine to check that ATCS is in the ATPneumatics operational range and update methods to use routine. (`DM-44628 <https://rubinobs.atlassian.net/browse/DM-44628>`_)
- Update BaseCalSys.setup_electrometers to setup electrometer mode, range, and integration time from input parameters. (`DM-44670 <https://rubinobs.atlassian.net/browse/DM-44670>`_)
- Update ATCalSys.prepare_for_flat to call setup_electrometer. (`DM-44670 <https://rubinobs.atlassian.net/browse/DM-44670>`_)
- Update atcalsys configuration such that the electrometer exposure time is similar to the camera exposure time and to include the additional electrometer configuration. (`DM-44670 <https://rubinobs.atlassian.net/browse/DM-44670>`_)
- Update MTCS to add a new disable_m2_balance_system method. (`DM-44824 <https://rubinobs.atlassian.net/browse/DM-44824>`_)
- Update MTCS run_m2_actuator_bump_test to wait until the bump test finishes before returning. (`DM-44824 <https://rubinobs.atlassian.net/browse/DM-44824>`_)
- Added PTC curve configurations to ATCalSys.yaml. (`DM-45219 <https://rubinobs.atlassian.net/browse/DM-45219>`_)


Bug Fixes
---------

- Update ATCalSys so that the filter scans have the correct wavelength range. (`DM-44670 <https://rubinobs.atlassian.net/browse/DM-44670>`_)


v0.36.0 (2024-06-01)
====================

New Features
------------

- Move calibration_config.yaml data file to atcalsys.yaml and add information required by the ATCalsys class now. (`DM-44454 <https://rubinobs.atlassian.net/browse/DM-44454>`_)
- Add __init__ file to data directory to make it a discoverable module. (`DM-44454 <https://rubinobs.atlassian.net/browse/DM-44454>`_)
- Add new get_data_path utility method to retrieve path to the data directory. (`DM-44454 <https://rubinobs.atlassian.net/browse/DM-44454>`_)
- In ``auxtel/atcalsys``, implement changes to match refactoring of the BaseCalsys class.

  This is a major rework of the class, implementing some of the high level functionality that allows one to take a set of calibrations. (`DM-44454 <https://rubinobs.atlassian.net/browse/DM-44454>`_)
- In ``base_calsys``, refactor of the base class to capture some of the lessons learned while writting the calibration script. (`DM-44454 <https://rubinobs.atlassian.net/browse/DM-44454>`_)
- Implement base_tcs start_tracking method. (`DM-44611 <https://rubinobs.atlassian.net/browse/DM-44611>`_)


Bug Fixes
---------

- In BaseTCS class, fix call to offsetRADEC. (`DM-44454 <https://rubinobs.atlassian.net/browse/DM-44454>`_)


Documentation
-------------

- Update towncrier configuration to use jira cloud path for tickets. (`DM-44454 <https://rubinobs.atlassian.net/browse/DM-44454>`_)


v0.35.0 (2024-05-31)
====================

New Features
------------

- Started atcalsys.py, which builds on top of basecalsys.py
  Includes all functions needed to build SalScript for creating flat field calibrations on the AuxTel (`DM-43627 <https://rubinobs.atlassian.net/browse/DM-43627>`_)


API Removal or Deprecation
--------------------------

- Remove support for handling authorization.
  This feature was removed from the system with ts-xml 21. (`DM-44366 <https://rubinobs.atlassian.net/browse/DM-44366>`_)


Other Changes and Additions
---------------------------

- Update conda recipe to use ts-conda-build=0.4. (`DM-44028 <https://rubinobs.atlassian.net/browse/DM-44028>`_)


v0.34.0 (2024-04-24)
====================

New Features
------------

- In `atcs.py` add methods to open/close the AuxTel dome dropout door. (`DM-41805 <https://rubinobs.atlassian.net/browse/DM-41805>`_)
- Added base_calsys and corresponding documentation. (`DM-42865 <https://rubinobs.atlassian.net/browse/DM-42865>`_)
- In ``auxtel/atcs``, update vent elevation to 17 degrees. (`DM-43038 <https://rubinobs.atlassian.net/browse/DM-43038>`_)
- In ``auxtel/atcs``, update dome_vent_open_shutter_time to 30s so we can run vent anytime during the day. (`DM-43038 <https://rubinobs.atlassian.net/browse/DM-43038>`_)
- In ``maintel/mtcs.py``, ignore dome elevation in the monitoring loop.
  The current version of the MTDome is not handling the wind screen/elevation axis so we will ignore it for the time being. (`DM-43038 <https://rubinobs.atlassian.net/browse/DM-43038>`_)
- In ``base_tcs.py``, update vent azimuth to keep 90 degrees away from the dome azimuth. (`DM-43038 <https://rubinobs.atlassian.net/browse/DM-43038>`_)


v0.33.0 (2024-02-12)
====================

New Features
------------

- In ``base_tcs.py`` add a ``slew_ephem_target`` method that allow both telescopes to track a target based on an ephemeris file. (`DM-41339 <https://rubinobs.atlassian.net/browse/DM-41339>`_)
- In ``maintel/mtcs.py``, update ``move_p2p_radec`` to check that the mtcs is in ENABLED state while moving. (`DM-41593 <https://rubinobs.atlassian.net/browse/DM-41593>`_)
- In `mtcs.py`, update `MTCS._slew_to` to enable compensation mode in the relevant components before a slew. (`DM-42132 <https://rubinobs.atlassian.net/browse/DM-42132>`_)
- In ``mtcs.py`` add a ``set_m1m3_controller_settings`` method that allows setting m1m3 slew controller settings. (`DM-42402 <https://rubinobs.atlassian.net/browse/DM-42402>`_)


Bug Fixes
---------

- Fix some type annotation issue in ``RemoteGroup``.

  Update ``ATCS.stop_all`` to remove return. (`DM-42046 <https://rubinobs.atlassian.net/browse/DM-42046>`_)
- In ``base_tcs.py``, update ``find_target_simbad`` to capture any exception when executing the remote query and retrow them as a ``RuntimeError``. (`DM-42478 <https://rubinobs.atlassian.net/browse/DM-42478>`_)
- Update MTCS Slew usages to add the compensationMode event for both hexapods. (`DM-42690 <https://rubinobs.atlassian.net/browse/DM-42690>`_)


Performance Enhancement
-----------------------

- Update ``MTCS`` slew control sequence to improve handling setting/unsetting the m1m3 slew flag before/after a slew starts/ends. (`DM-42046 <https://rubinobs.atlassian.net/browse/DM-42046>`_)


Other Changes and Additions
---------------------------

- In ``auxtel/atcs.py``, update prepare_for_vent to fully open the dome if ``partially_open_dome`` is selected.

  Reformat with black 24.

  Update .gitignore with latest ts-pre-commit-config setup. (`DM-42690 <https://rubinobs.atlassian.net/browse/DM-42690>`_)


v0.32.0 (2023-11-28)
====================

New Features
------------

- Add _overslew_azimuth feature to base_tcs class to slew past the target position and return. Set default to FALSE in base_tcs class and TRUE for atcs. (`DM-40913 <https://rubinobs.atlassian.net/browse/DM-40913>`_)
- Update ``MTCS`` class to support running M2 bump tests. (`DM-41111 <https://rubinobs.atlassian.net/browse/DM-41111>`_)
- Update overslew feature and add log messages.
  In ``mtcs``, add a check in move_p2p that the components are enabled while moving. (`DM-41538 <https://rubinobs.atlassian.net/browse/DM-41538>`_)


v0.31.1 (2023-10-25)
====================

Documentation
-------------

- Integrate towncrier for release notes and change log management. (`DM-41258 <https://rubinobs.atlassian.net/browse/DM-41258>`_)


Other Changes and Additions
---------------------------

- Updates to make the package compatible with salobj 8.
  Changes involves mostly updating how the async mock objects are created.
  Instead of relying in ts-idl and ts-salobj to generate specs for the remote's, use the newly introduced method in ts-xml. (`DM-40580 <https://rubinobs.atlassian.net/browse/DM-40580>`_)


v0.31.0
=======

* Add ``LSSTCam`` class to interface with the LSSTCam CSC using the ``BaseCamera`` interface.
* In ``maintel/mtcs.py``, add ``stop_rotator`` method to stop rotator movement.
* Add support for mtrotator cmd_stop and evt_controllerState in ``mock/mtcs_async_mock.py``.
* In ``constants/latiss_constants.py``, update blue300lppm_qn1, holo4_003, and holo4_001 sweet spots.
* Add new option to ``MTCS.move_rotator`` to allow the function to return before the rotator is in position.
* Export enum classes ``DOFName`` and ``ClosedLoopMode`` in ``enums.py``.

v0.30.5
=======

* Add ``DOFName`` enum to ``enums.py``
* Update atcs telescope and dome flatfield position following atwhitelight alignment.
* Use lsst.ts.xml.tables.m1m1 instead of ts.lsst.criopy for M1M3 FATable.
* In ``maintel/mtcs.py``, add exception to allow backwards compatability with M1M3 FATable import from ts.lsst.criopy.

v0.30.4
=======

* In ``latiss_constants.py``, add initial sweet spot for holo4_001 grating.

v0.30.3
=======

* In ``maintel/mtcs.py``:

  * Update hard point correction handlers to use ``evt_forceControllerState`` instead of ``evt_forceActuatorState``.
  * Add support for m1m3 setSlewFlag/clearSlewFlag.
  * Add ``forceControllerState`` to the list m1m3 events for the slew usage.

v0.30.2
=======

* Update ``pyproject.toml`` to remove usage of flake8 and black pytest plugins.
* Add github linting workflow.
* Add support for ``ts-pre-commit-config``.

v0.30.1
=======

* In ``maintel/mtcs.py``:

  * Add ``detailedState`` to list of Slew events for m1m3.

  * Change order of closing booster valves and enabling hardpoint corrections.

  * Update ``_handle_m1m3_hardpoint_correction_command`` to also skip ``salobj.base.AckTimeoutError``.

  * Add new ``wait_m1m3_settle`` and call it before closing the booster valve in ``m1m3_booster_valve`` context manager.

    For now this only waits for a pre-defined time, but in the future we should implement a better way to determine if M1M3 has settled or not.

* In ``base_tcs.py``, update ``_handle_in_position`` to not ignore timeout error when waiting for a new event in the waiting loop.

v0.30.0
=======

* In ``maintel/mtcs.py``:

  * Add ``forceActuatorState`` to mtm1m3 Slew usages.
  * Fix lower/raise m1m3 to handle m1m3 in engineering mode.
  * Update ``close_m1m3_booster_valve`` to enable force balance system before closing the booster valves.
  * Update ``open_m1m3_booster_valve`` to enter engineering mode and to disable m1m3 force balance system before opening the booster valves.
  * Update ``_handle_raise_m1m3`` and ``_handle_lower_m1m3`` to work around command timeout.
  * Add timeout when getting ``detailedState`` in ``_execute_m1m3_detailed_state_change``.
  * Add ``disable_m1m3_balance_system``.
  * Refactor ``enable_m1m3_balance_system`` to extract code into two general purpose private methods; ``_handle_m1m3_hardpoint_correction_command`` and ``_wait_force_balance_system_state``.

v0.29.2
=======

* In ``auxtel/atcs.py``, update the dome and telescope flat field position.

v0.29.1
=======

* In ``maintel/mtcs.py``, update MTCS usages to add booster valve status event to Slew usage.

v0.29.0
=======

* In ``tests/maintel/test_mtcs.py``:

  * Update ``test_slew_icrs`` to check that ``m1m3_booster_valve`` is correctly called while slewing.
  * Add unit tests for new move point to point methods.
  * Add unit tests for ``MTCS.m1m3_booster_valve``.

* In ``mock/mtcs_async_mock.py``, add mocking for the m1m3 booster valve.

* In ``maintel/mtcs.py``:

  * Add methods to move the telescope using point to point movement instead of slewing.
  * Update ``_slew_to`` method to use ``m1m3_booster_valve`` when executing a slew command.
  * Add a new async context manager ``m1m3_booster_valve`` to handle opening/closing the M1M3 booster valve for a particular operation.

v0.28.0
=======

* In ``maintel/mtcs.py``:

  * Update ``get_m1m3_bump_test_status`` to accept ``actuator_id`` as an input parameter and return the primary and secondary test status.
    The secondary test status is ``None`` if the actuator has no secondary element.

  * Extract the code that parses the M1M3 ``forceActuatorBumpTestStatus`` into a separate method, ``_extract_bump_test_status_info``.

  * Use ``_extract_bump_test_status_info`` in ``_wait_bump_test_ok`` to parse the information from the M1M3 ``forceActuatorBumpTestStatus``.

  * Update docstring of ``get_m1m3_actuator_index`` and ``get_m1m3_actuator_secondary_index`` to document exception raised by the methods and include a "See Also" session.

* In ``mock/mtcs_async_mock.py``, improve mocking of the m1m3 actuator testing to more closely resemble m1m3 behavior.

v0.27.1
=======

* In ``maintel/mtcs.py``:

  * Add a specific timeout for the hard point test that is long enough to allow it to execute.
  * Update ``run_m1m3_hard_point_test`` to wait for ``_wait_hard_point_test_ok``, catch timeout exceptions and raise a runtime error instead.
  * Update ``enter_m1m3_engineering_mode`` to ignore timeout error in ``cmd_enterEngineering``.

v0.27.0
=======

* In ``auxtel/atcs.py``, add new ``offset_aos_lut`` method. 

* In ``maintel/mtcs.py``:

  * Add support for running/stopping m1m3 actuator bump test.
  * Add support for running/stopping m1m3 hard point tests.
  * Add support for entering/existing m1m3 engineering mode.
  * Update ``MTCS._wait_for_mtm1m3_detailed_state`` to accept a set of expected detailed states instead of a single value.
  * Pass timeout to ``aget`` in ``MTCS._wait_for_mtm1m3_detailed_state``.
  * Update ``MTCS._handle_m1m3_detailed_state`` to pass a set with the expected state when calling ``MTCS._wait_for_mtm1m3_detailed_state``.
  * Fix typos in docstring.
  * Add method to assert that m1m3 is in one of a set of detailed states.

* Add github action to check that version history was updated.

* Setup ts_cRIOpy as part of the dependencies for the CI.

* Add ts_cRIOpy to the eups dependency table.

* Modernize conda recipe and include ts-criopy as a dependency.


v0.26.0
=======

* In ``base_tcs.py``, add new ``offset_pa`` method.
* In ``auxtel/atcs.py``, minor improvements in ``offset_done`` method.
* In ``auxtel/atcs.py``, update ``open_dome_shutter`` to also work when the dome is partially opened.

v0.25.0
=======

* In ``BaseTCS``, add new ``offset_rot`` method to allow offsetting the rotator position.

v0.24.3
=======


* In ``tests/auxtel/test_atcs.py``,  implement some small improvements in the ``ATCS`` test case.

  * Call ``atcs.enable_dome_following`` in all ``test_slew``.
    This will make sure the ``monitor_loop`` runs and checks the dome position.

  * Add two new slew tests:

    * Test slew icrs when telescope timeout arriving in position.

    * Test slew icrs when dome timeout arriving in position.

* In ``mock/atcs_async_mock.py``, add mocking for the atdome move azimuth command and in position event.

* In ``base_tcs.py``, update ``BaseTCS._handle_in_position`` debug message to also display the timeout.

* In ``auxtel/atcs.py``, update ``ATCS.monitor_position`` to make log messages more similar to the ones in ``MTCS``.

* In ``auxtel/atcs.py``, update  ``ATCS.wait_for_inposition`` to improve reporting of timeout failures.
  Instead of appending coroutines to the `tasks` list, use ``asyncio.create_task`` and give names to each of the tasks.
  Then, instead of simply gathering the tasks, which leads to uncomprehensive  tracebacks when tasks timeouts, capture any exception and reprocess the error messages re-raising them as `RuntimeError` with a more comprehensive message.

* In ``auxtel/atcs``, update ``ATCS._slew`` to use the more robust ``asyncio.create_task`` instead of ``ensure_future`` when scheduling background tasks.

v0.24.2
=======

* Format souce files with black 23.
* Update pre-commit hook versions.

v0.24.1
=======

* In ``constants/latiss_constants.py``, add sweetspot for new grating.
* Update Jenkinfile to stop using root.

v0.24.0
=======

* In ``BaseTCS``, update ``radec_from_azel`` to convert ``AltAz`` into a ``SkyCoord`` before converting to ``ICRS``.
  Directly converting from ``AltAz`` into ``ICRS`` will be deprecated in the future.

* In ``ATCS``:

  * Add methods to enable/disable ataos corrections.
  * Add new method ``is_dome_homed`` to check if the dome is homed or not.
  * Update ``shutdown`` to use ``disable_ataos_corrections`` instead of sending the command directly to the component.
  * Update ``home_dome`` to add new ``force`` option and to check if dome is homed already.
  * Rename ``azimuth_open_dome`` -&gt; ``dome_open_az``.
  * Upadate ``prepare_for_onsky`` to use the ``enable_ataos_corrections`` instead of sending the command directly,
  * Add new method ``stop_dome`` to stop motion of the atdome.
  * Update ``prepare_for_flatfied`` home dome.
  * ``close_dome`` change default option to ``force=True``.
  * Update ``close_dome`` to send the command when ``force=True`` even if the dome is not reporting as opened.
  * Update ``prepare_for_onsky`` to disable ataos corrections before opening m1.
  * Update ``prepare_for_flatfield`` to disable ataos corrections before opening the mirror covers and enable them afterwards.

v0.23.3
=======

* In ``BaseCamera``, update ``_handle_take_stuttered`` to remove call to ``cmd_clear``.
* In ``BaseCameraAsyncMock``, update ``assert_take_calibration`` to remove call to ``cmd_clear``.

v0.23.2
=======

* In ``ScriptQueue``:

  * Make sure ``get_script_schema`` can handle condition where multiple ``configSchema``, for different scripts, are published while it is executed.
  * Fix text separator when splitting list of scripts in ``list_standard_scripts`` and ``list_external_scripts`.

v0.23.1
=======

* Add support for authorization.

v0.23.0
=======

* In ``MTCS``:

  * Fix doctring and logged information about behaviour when hexapod compensation mode is on in ``move_camera_hexapod`` and ``move_m2_hexapod``, 

  * Add new methods `offset_m2_hexapod` and `offset_cam_hexapod` that offset the M2 and camera hexapod respectively.

    This method can be used when performing optical alignment with the MTAlignment component or when performing optical alignment with curvature wavefront sensing to take the intra/extra focal data.

v0.22.1
=======

* Update ``ATCS`` unit test to use the new ``ATCSAsyncMock`` class.

* Update ``MTCS`` unit test to use the new ``MTCSAsyncMock`` class.

* Add new ``MTCSAsyncMock`` class that implements ``RemoteGroupAsyncMock`` for ``MTCS``.

* Add new ``ATCSAsyncMock`` class that implements ``RemoteGroupAsyncMock`` for ``ATCS``.

* In ``MTCS``:
  
  * Add compatibility with xml>12.

  * Update ``reset_m1m3_forces`` to use ``mtm1m3.cmd_clearActiveOpticForces`` instead of setting the forces to zero.

* Update pre-commit config file with latest version of libraries and to add support for `isort` and `mypy` and `pyproject.toml` to support `isort`.

* In ``RemoteGroupAsyncMock``:

  * In ``get_side_effects_for``:

    * Change return type to ``Dict[str, Any]``.

    * Stop wrapping side effects in mocks.

    * Add side effect to handle flushing events.

  * Add ``get_all_checks`` method that creates a copy of the ``check`` attribute from the ``remote_group``.

  * Override super class ``run`` method to setup random DDS partition prefix and set LSST_SITE.

  * In ``setup_basic_mocks``, setup data structure to support handling summary state.

  * In ``get_spec_from_topics``, add ``DataType`` to topic spec.

  * In ``get_component_topics``, add "tel" prefix to telemetry topics.

  * Add ``flush_summary_state_for`` to create a side effect to mock the ``flush`` method.

  * In ``set_summary_state_for``, fix ``set_summary_state`` to append a copy of summary state to the ``summary_state_queue``.

  * In ``next_summary_state_for``, fix ``next_summary_state`` to return the value of ``summary_state`` instead of popping the value from ``summary_state_queue``.

  * In ``set_component_commands_arguments``, fix filtering of which topics are commands.

* Ignore files generated by pypi.

v0.22.0
=======

* Add new type hints to allow type annotation of methods and coroutines that has signature like ``func(**kwargs: Any) -> None``.

* Improve how ``RemoteGroupAsyncMock`` mocks a ``RemoteGroup``.

  Instead of making each ``Remote`` a free form ``AsyncMock``, create a spec based on the component interface.
  This means, trying to assess a member that is not part of the CSC interface raises an ``AttributeError`` exception, which is usefull to catch interface changes, like topics that are renamed and such.
  

  It also adds functionality to catch changes in topic payloads.
  For commands, create methods that check command call payloads and raise exception if a topic attribute is not part of the command definition.
  For events and telemetry, add a method to create ``SimpleNamespace`` instances from the topics structure.

* Add new ``BaseCameraAsyncMock`` mock class, to facilitate mocking/testing classes derived from ``BaseCamera`` without the need to use the middleware.
  This considerably reduces the time needed to setup the classes for testing allowing us to expand the test coverage considerably without too much of a time penalty.

* Refactor ``ATCS`` tests to use the new ``BaseCameraAsyncMock`` class.

* Refactor ``ComCam`` tests to use the new ``BaseCameraAsyncMock`` class.

* In ``BaseCamera``, add check that stuttered image is supported by the particular interface.
  This is defined by the set of commands required to drive sturreted images.

* Add ``GenericCamera`` class to interface with the generic camera CSC using the ``BaseCamera`` interface.

* In ``ATCS``, change log level of message sent when stopping monitor loop from warning to debug.

* In ``MTCS``, remove workaround for rotator trajectory issues that prevented us from doing more than one slew at a time.

* Update ``.gitignore`` to ignore all ``.log`` files.

v0.21.0
=======

* In ``BaseTCS`` class:

  * Add new functionality to allow alternative rotator angles to be specified.
    This features consists of two methods, ``BaseTCS.set_rot_angle_alternatives`` and a generator ``BaseTCS.get_rot_angle_alternatives``.
    By default the altenative angles are +/- 180 and +/- 90 degrees.

    ``BaseTCS.get_rot_angle_alternatives`` recieves a desired angle and will ``yield`` a sequence of numbers consisting of the original number first, then a the original number + the alternative.
    Therefore, by default, if one calls ``BaseTCS.get_rot_angle_alternatives``, it will yield the sequence 0, 180, -180, 90, -90.

    It is possible to override the sequence of alternaive angles by calling ``BaseTCS.set_rot_angle_alternatives``, passing a new sequence of numbers.
    It is not necessary to pass the 0 value and duplicated entries are removed.
  
  * In ``slew_icrs`` use new rotator angle alternatives to cycle throught different rotator angles when the value requested is outside the rotator limits.

v0.20.1
=======

* Fix issue with ``LATISS.setup_instrument`` which would fail if linear stage position was passed as ``None``, which is a valid entry.
* Add unit test for ``LATISS.setup_instrument``.

v0.20.0
=======

* Update build configuration to use ``pyproject.toml``.
* Implement type-checking in the entire package.

v0.19.0
=======

* Add new high-level class to interact with the ``ScriptQueue``, and child classes to interact with ATQueue and MTQueue.

v0.18.2
=======

* Add support for stuttered image keywords.
* In ``BaseCamera``:

  * Update ``_handle_take_stuttered`` method to call ``set`` and then ``start`` separately, so it can set the ``timeout`` parameter.

v0.18.1
=======

* `MTCSMock`: stop calling lsst.ts.salobj.topics.WriteTopic.write with arguments.

v0.18.0
=======

* In `BaseCamera`:

  * Add support for new images types: ACQ, CWFS, FOCUS.

  * Refactor `BaseCamera.expose` to use the new `CameraExposure` data class and break it down into smaller pieces.

  * Add support for stuttered image.
    This image type opens the camera shutter, start the exposure manually and then allow users to shift the readout manually.
    This allow us to produce "stuttered" images with starts shifting in the read direction at each iteration.

  * Add support for taking snaps in `take_object`.

* Add unit tests for stuttered images for ComCam.

* Add unit tests for stuttered images for LATISS.

* Add support for stuttered images in `ComCamMock`.

* Add support for stuttered image in `LatissMock`.

* Add new dataclass CameraExposure to host parameters for exposures.

* Add unit test for new image types for ComCam.

* Add unit tests for new image types for LATISS.


v0.17.0
=======

* In `test_atcs`, rename `test_monitor` -> `test_monitor_position_dome_following_enabled`, and make sure dome following is enabled before running test.
  Add `test_monitor_position_dome_following_disabled` test to check condition when dome following is disabled.
* Update ComCamMock to correctly take into account `numImages > 1`.
* In `tests/maintel/test_mtcs.py`:
  * Add unit test for `MTCS.move_rotator` method.
  * Fix typo `mtmout` -> `mtmount` in two method names.
* In ATCS, update how _slew handles monitor.
* In MTCS, add `move_rotator` method to handle moving the rotator and waiting for the movement to complete.
* In `BaseCamera`, use `numImages` feature from Camera to take multiple images, instead of looping.
* In `ATCS.monitor_position`, handle condition when dome following is disabled but dome checking is enabled.
* In `MTCS._slew_to`, juggle rotator position by 0.1 degrees when working around trajectory problem.
  This will make sure the rotator moves a bit, thus resetting the trajectory.
* In `ATCS.slew_dome_to`, fix handling of `monitor_position` by creating a background task.
* In `ATCS.slew_dome_to`, improve handling dome positioning.
  The ATDome will overshoot if slew is large enough, the method will send a move command, use `_handle_in_position` to determine when the dome is in position and then check that the dome is still in position afterwards.
  If it is not, it will iterate up to `_dome_slew_max_iter` times.
  The method is also not using the internal dome in position flag, which only checks if the dome is obscuring the telescope or not.
  This algorithm is only suitable for on sky slewing operation and not for when we are positioning the dome.
* In `ATCS.slew_dome_to`, use `_handle_in_position` to determine when dome is in position.
* Update `MTCS.wait_for_rotator_inposition` to use `_handle_in_position`.

v0.16.1
=======

* Update to black 22.

v0.16.0
=======

* Change archiver references to oods ones due to image creation process change (DMTN-143).

v0.15.0
=======

* Update for ts_salobj v7, which is required.
  This also requires ts_xml 11.
* Rename ``settings`` to ``overrides``.
* `RemoteGroup`: use "" as the default override for all components.
  Remove the ``inspect_settings`` method and rename ``expand_settings`` to ``expand_overrides``.

v0.14.0
=======

* Remove usage of deprecated methods from salobj.
* In `BaseTCS`:
  * Fix handle in position event to use `flush=True` when dealing with potential race condition.
  * Change default value of `stop_before_slew` parameter in slew commands from `True` to `False`.
* In `ATCS`: 
  * Remove secondary check for in position condition.
    This check was a workaround for a problem we had with the ATMCS `inPosition` event long ago but it was now causing problems.
  * Fix `monitor_position` unit tests.
  * Implement `handle_in_position_event` for ATMCS.
  * Update unit tests for new default value of `stop_before_slew`.
  * Mark `test_find_target` as flaky. This test reaches Simbad remote server, which can be flaky sometimes.
  * Augment atdometrajectory mocks in tests/auxtel/test_atcs.py.
  * In `slew_dome_to`, wait only for atdome to arrive in position.
* In `MTCS`:
  * Move rotator synchronization to outside "stop_before_slew".
  * Update unit tests for new default value of `stop_before_slew`.

v0.13.2
=======

* Fix unit test failure in `slew_object` due to coordinate convertion issue.

v0.13.1
=======

* Make MTCS non-concurrent.
* In `BaseTcs` add interface to enable/disable concurrent operation.
* In `RemoteGroup` implement mechanism to prevent concurrent operation.

v0.13.0
=======

* Update MTCSMock for the latest xml.
* Add unit tests for additional keywords in LATISS and ComCam.
* In `BaseCamera`:
  * Implement reason and program keywords on the `take_<img_type>` methods.
  * In `BaseCamera.next_group_id` replace all occurrences of "-" and ":" by empty strings.
  * Add `reason` and `program` to the interface of `expose`
  * Provide a base implementation for `expose`.
  * Add new abstract method `parse_sensors`, that receives a `sensors` string and return a valid `sensors` string for the particular implementation.
  * Add new abstract property `camera` that should return the remote to the camera.
  * Add new `get_key_value_map` method that parses its inputs into a valid `keyValueMap` entry for the cameras takeImage command.
* In `ComCam`:
  * Remove specialized implementation of the `expose` method.
  * Add new abstract property, `camera`.
  * Add new abstract method `parse_sensors`
  * Update `take_spot` to implement test_type, reason and program keywords.
* In `LATISS`:
  * Remove specialized implementation of the `expose` method.
  * Add new abstract property, `camera`.
  * Add new abstract method `parse_sensors`

v0.12.1
=======

* Update expand `RemoteGroup.inspect_settings` to deal with non-configurable components.

v0.12.0
=======

* Update the code to use ts_utils.
* Modernize the unit tests to use bare asserts.

v0.11.2
=======

* Update `mock.BaseGroupMock` to be compatible with xml 10.1 and sal 6.
* In `MTCS`:
  * Disable ccw_following check on mtcs slew.
  * Implement work around to rotator trajectory problem that cannot complete 2 subsequent moves.
    The work around consist of sending a move command to the rotator current position then stopping, thus resetting the trajectory.

v0.11.1
=======

* Update conda recipe to add new dependencies; pandas and scipy.
* Update setup.py to include `.pd` files.
* Unit tests for `BaseTCS` new catalog feature.
* In `BaseTCS`:
  * move `find_target` code into `find_target_simbad`. In `find_target`, use `find_target_local_catalog` if catalog is loaded or try `find_target_simbad` otherwise or if it fails to find a target in the local catalog.
  * implement method to find target given an az/el position, magnitude range and radius.
  * implement method to query objects from the local catalog, when a catalog is loaded, or query `Simbad` if the catalog is not loaded or the object is not found in the local catalog.
  * add functionality to manage local catalogs, which includes:
    * list available catalogs.
    * load a catalog from the list of available catalogs.
    * check if a catalog was loaded.
    * clear catalog.
* Add `BaseTCS.object_list_get_all` method to retrieve a list of all the object names in the object list.
* Add utility function to return the path to the catalog module.
* Add `catalogs` module to store local object catalogs.
* Add `hd_catalog_6th_mag.pd` catalog file.
  This is a cut out of the HD catalog with southern stars brighter than 6th magnitude, used for testing the package.
  It contains roughly 1500 objects.
* Setup `.gitattributes` to track `*.pd` files with git large file storage.
* In `MTCS`:
  * replace `axesInPosition` by `elevationInPosition` and `azimuthInPosition` on all usages.
  * fix for xml 10.0.0. Event `axesInPosition` was removed, need to use `elevationInPosition` and `azimuthInPosition` instead.
* In `ATCS`:
  * add `ATDomeTrajectory.evt_followingMode` to `Slew` usage.
  * `assert_m1_coorection_disabled` deal with situation where no `correctionEnabled` event is seen.
* Update Jenkinsfile to pull git lfs files before running tests.

v0.11.0
=======

* In MTCS: 
  * add longer timeout for raising/lowering the system.
  * implement `reset_m2_hexapod_position`.
  * implement `reset_camera_hexapod_position`.
  * implement `move_m2_hexapod`.
  * implement `move_camera_hexapod`.
  * implement `enabled_compensation_mode` and `disable_compensation_mode`.
  * implement `reset_m2_forces`.
  * implement `enable_m2_balance_system`.
  * implement `reset_m1m3_forces`.
  * omplement enable_m1m3_balance_system.
  * Implement abort_raise_m1m3.
  * implement lower_m1m3 method.
  * add method to handle raising m1m3.
  * add methods to handle m1m3 detailed state.
  * Implement `MTCS.raise_m1m3` method.
  * Implement `MTCS._execute_m1m3_detailed_state_change`, a method that executes a command that change M1M3 detailed state and handle waiting for it to complete.
* In `test_mtcs`:
  * implement `test_check_mtm1m3_interface`.
  * add support for summary state and heartbeat on the mocks.
  * rename import of `astropy.units` from `u` to `units`.
  * add support for summary state and heartbeat on the mocks.
  * add logger to `TestMTCS`.
* Fix `get_software_versions` docstring.
* Add new `BaseTCS._handle_in_position` method to take care of in position event in a generic way.
* Unit tests for `get_work_components`.
* In `RemoteGroupd` add `get_sfotware_versions` method to return the last sample of `softwareVersions` event for all components or a subset.
* Fix unit test on get_simulation_mode.
* In test_base_group, implement usage of `DryTest` to allow implementation of faster unit tests that don't require Remotes/Controllers.
* Use `_aget_topic_samples_for_components` in `get_simulation_mode`
* In `RemoteGroup`: 
  * add new usages:
    * CheckSimulationMode
    * CheckSoftwareVersions
    * DryTest
  * add new utility method `_aget_topic_samples_for_components` to get generic samples.
  * usages `All` add new generic events.
  * add `RemoteGroup.get_work_components` method.
  * add new method `get_simulation_mode` that returns a dictionary with the last sample of the event `simulationMode` for all components or a subset specified in the `components` input parameter.
  * `RemoteGroup.set_state`  use new method `get_work_components`.
  * add `RemoteGroup.get_work_components` method. 
    This method receives a list of component names, and either raise an exception (if one or more components are not part of the group) or return a list of components. If called with `None`, return the name of all components.
* Add new utility method `handle_exeception_in_dict_items`, to handle exception stored in dictionaries items.
* Add new utility method `handle_exeception_in`, to handle exception stored in dictionaries items.
* Remove the delay in ComCam image taking.
* In ATCS:
  * Increase timeout in open/close m1 cover.
  * add focusNameSelected. to startUp usages.
  * add ataos `correctionEnabled` event to usages.
  * add atdometrajectory followingMode event as a dependency to usages.
  * update `prepare_for_onsky` to allow enabling dome following at the end.
  * Make `ATCS` more resilient when the dome following is disabled.

v0.10.3
=======

* Add `DryTest` to `LATISSUsages`. 
  This is useful for unit testing.
* In open/close m1 cover and vents check that m1 correction is disabled before proceeding.
* Add feature to check that ATAOS m1 correction is disabled.
* In `BaseTCS.find_target` fix magnitude range to use input parameter instead of hard coded value.

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
