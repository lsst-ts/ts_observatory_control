.. _guider_roi_scripts:

##################
GuiderROI Scripts
##################

Scripts for ingesting and testing guide star catalog data with vignetting corrections for the Rubin Observatory LSSTCam guider system.

Overview
========

Instrument vs Repository
-------------------------

At the Rubin Observatory summit, Butler repositories are organized by instrument:

- **LSSTCam**: Main camera repository (default for guider ROI data)
- **LATISS**: Auxiliary Telescope repository

Each instrument has its own Butler repository with instrument-specific metadata, collections, and calibrations. The ``--repo-name`` option specifies which instrument's repository to use.

Repository Setup
================

Clone and Checkout Branch
--------------------------

.. code-block:: bash

    git clone https://github.com/lsst-ts/ts_observatory_control.git
    cd ts_observatory_control
    git checkout tickets/OSW-1064

Environment Setup (Summit)
---------------------------

.. code-block:: bash

    # Load LSST software stack
    source /opt/lsst/software/stack/loadLSST.bash

    # Setup required packages
    setup lsst_distrib
    setup summit_utils

    # Set PYTHONPATH to use local development version
    export PYTHONPATH=${PWD}/python:${PYTHONPATH}

Scripts
=======

ingest_guider_data.py
---------------------

Ingests guide star catalog and vignetting correction data into a Butler repository.

**Summit Usage (LSSTCam - default):**

.. code-block:: bash

    python python/lsst/ts/observatory/control/data/scripts/guider_roi/ingest_guider_data.py \
        --ingested-by "Your Name <your.email@lsst.org>" \
        --contact "your.email@lsst.org" \
        --catalog-path /path/to/Monster_guide \
        --vignetting-file /path/to/vignetting_vs_angle.npz \
        --collection guider_roi_data

**Summit Usage (LATISS):**

.. code-block:: bash

    python python/lsst/ts/observatory/control/data/scripts/guider_roi/ingest_guider_data.py \
        --repo-name LATISS \
        --ingested-by "Your Name <your.email@lsst.org>" \
        --contact "your.email@lsst.org" \
        --catalog-path /path/to/Monster_guide \
        --vignetting-file /path/to/vignetting_vs_angle.npz \
        --collection guider_roi_data

.. note::
   At the summit, the script uses ``makeDefaultButler()`` which automatically configures the Butler for the specified instrument/repository (LSSTCam by default).

**Local Testing:**

.. code-block:: bash

    python python/lsst/ts/observatory/control/data/scripts/guider_roi/ingest_guider_data.py \
        --repo-path butler_data \
        --ingested-by "Your Name <your.email@lsst.org>" \
        --contact "your.email@lsst.org" \
        --catalog-path /path/to/Monster_guide \
        --vignetting-file /path/to/vignetting_vs_angle.npz

guider_roi_test_script.py
--------------------------

Tests GuiderROI functionality with ingested data.

**Summit Usage (LSSTCam - default):**

.. code-block:: bash

    python python/lsst/ts/observatory/control/data/scripts/guider_roi/guider_roi_test_script.py \
        --collection guider_roi_data \
        --pixel 1063

**Summit Usage (LATISS):**

.. code-block:: bash

    python python/lsst/ts/observatory/control/data/scripts/guider_roi/guider_roi_test_script.py \
        --repo-name LATISS \
        --collection guider_roi_data \
        --pixel 1063

**With specific coordinates:**

.. code-block:: bash

    python python/lsst/ts/observatory/control/data/scripts/guider_roi/guider_roi_test_script.py \
        --collection guider_roi_data \
        --ra 45.0 --dec -30.0

**Local Testing:**

.. code-block:: bash

    python python/lsst/ts/observatory/control/data/scripts/guider_roi/guider_roi_test_script.py \
        --repo-path butler_data \
        --collection guider_roi_data \
        --pixel 1063

Butler CLI Inspection
=====================

Get Butler Repository Path (Summit)
------------------------------------

For **LSSTCam**:

.. code-block:: bash

    REPO_PATH=$(python -c "
    import sys
    import logging
    logging.basicConfig(stream=sys.stderr, level=logging.CRITICAL)
    from lsst.summit.utils import makeDefaultButler
    butler = makeDefaultButler('LSSTCam', writeable=False)
    print(butler._config.configFile)
    " 2>/dev/null)

For **LATISS**:

.. code-block:: bash

    REPO_PATH=$(python -c "
    import sys
    import logging
    logging.basicConfig(stream=sys.stderr, level=logging.CRITICAL)
    from lsst.summit.utils import makeDefaultButler
    butler = makeDefaultButler('LATISS', writeable=False)
    print(butler._config.configFile)
    " 2>/dev/null)

Query Collections
-----------------

.. code-block:: bash

    butler query-collections $REPO_PATH guider_roi_data

**Example Output:**

.. code-block:: text

          Name      Type
    --------------- ----
    guider_roi_data RUN

Query Dataset Types
-------------------

.. code-block:: bash

    butler query-dataset-types --collections guider_roi_data $REPO_PATH

**Example Output:**

.. code-block:: text

                  name              
    --------------------------------
    guider_roi_monster_guide_catalog
    guider_roi_vignetting_correction

Query Datasets
--------------

Query all datasets (specify ``'*'`` to avoid future warning):

.. code-block:: bash

    butler query-datasets --collections guider_roi_data $REPO_PATH '*'

**Example Output:**

.. code-block:: text

                  type                     run                        id                  healpix5
    -------------------------------- --------------- ------------------------------------ --------
    guider_roi_monster_guide_catalog guider_roi_data 10640b18-b477-43cd-9fe5-3392c4c5307f        0
    guider_roi_monster_guide_catalog guider_roi_data 4e720ea4-4418-4ebb-b620-78a021de75d1        1
    guider_roi_monster_guide_catalog guider_roi_data d97b2cb4-afa6-4b9b-944d-ec03e4fb946e        2
    ...
    guider_roi_monster_guide_catalog guider_roi_data 7944151a-a93d-4a0e-8a5c-43bdcafaf004    12287

                  type                     run                        id                 
    -------------------------------- --------------- ------------------------------------
    guider_roi_vignetting_correction guider_roi_data 9795d631-ee60-4391-af7d-c7228a024383

Query only catalog datasets:

.. code-block:: bash

    butler query-datasets --collections guider_roi_data $REPO_PATH guider_roi_monster_guide_catalog

Query Specific HEALPix Pixel via Python API
--------------------------------------------

**Interactive Python (LSSTCam):**

.. code-block:: python

    from lsst.summit.utils import makeDefaultButler

    # Get Butler for LSSTCam
    butler = makeDefaultButler('LSSTCam', writeable=False)

    # Get catalog for specific HEALPix pixel
    catalog = butler.get(
        "guider_roi_monster_guide_catalog",
        dataId={"healpix5": 1063},
        collections=["guider_roi_data"]
    )

    print(f"Found {len(catalog)} stars in HEALPix pixel 1063")
    print(f"Columns: {catalog.colnames}")

**Interactive Python (LATISS):**

.. code-block:: python

    from lsst.summit.utils import makeDefaultButler

    # Get Butler for LATISS
    butler = makeDefaultButler('LATISS', writeable=False)

    # Get catalog for specific HEALPix pixel
    catalog = butler.get(
        "guider_roi_monster_guide_catalog",
        dataId={"healpix5": 1063},
        collections=["guider_roi_data"]
    )

    print(f"Found {len(catalog)} stars in HEALPix pixel 1063")
    print(f"Columns: {catalog.colnames}")

Data Structure
==============

Catalog Datasets
----------------

- **Type**: ``guider_roi_monster_guide_catalog``
- **Storage Class**: ``ArrowAstropy`` (Parquet-backed Astropy tables)
- **Dimensions**: ``healpix5`` (HEALPix level 5, nside=32)
- **Contents**: Guide star positions, magnitudes (ugrizy + Gaia G), proper motions, quality flags

Vignetting Dataset
------------------

- **Type**: ``guider_roi_vignetting_correction``
- **Storage Class**: ``VignettingCorrection``
- **Dimensions**: None (single global dataset)
- **Contents**: Vignetting correction as function of angle from boresight

Metadata
========

Both catalog and vignetting datasets include sidecar metadata YAML files:

- ``guider_roi_vignetting.metadata.yaml``
- ``guider_roi_star_catalog.metadata.yaml``

Place these files either:

1. Next to the data files (highest priority)
2. In ``python/lsst/ts/observatory/control/data/`` (fallback)

Troubleshooting
===============

Script not finding Butler
-------------------------

**Error**: ``ERROR: Butler repository not found``

**Solution**: Ensure you're either:

- On the summit with ``summit_utils`` available (don't use ``--repo-path``, optionally specify ``--repo-name LSSTCam`` or ``--repo-name LATISS``)
- Using a local repository (provide ``--repo-path``)

PYTHONPATH issues
-----------------

**Error**: ``ModuleNotFoundError: No module named 'lsst.ts.observatory.control'``

**Solution**: Set PYTHONPATH before running:

.. code-block:: bash

    export PYTHONPATH=/path/to/ts_observatory_control/python:${PYTHONPATH}

No data available
-----------------

**Error**: ``ERROR: No test data available``

**Solution**: First run ``ingest_guider_data.py`` to populate the Butler repository with catalog and vignetting data.

