# Guider ROI Extras

Utilities for testing GuiderROIs functionality with Butler and test data generation.

## Files

- **`guider_roi_test.ipynb`** - Example notebook demonstrating GuiderROIs usage with Butler and file-based modes
- **`generate_test_guider_data.py`** - Generates guider catalog and vignetting data for testing
- **`ingest_guider_data.py`** - Ingests catalog and vignetting data into a local Butler repository with custom dataset names
- **`data/`** - Directory for generated test data (catalogs, vignetting, Butler repository)

## Quick Start

### 1. Generate Test Data and Create Butler Repository

```bash
# Run the complete example notebook (recommended)
jupyter notebook guider_roi_test.ipynb

# Or generate data manually:
python generate_test_guider_data.py --target-ra 120.0 --target-dec -45.0 --neighbor-radius 2
python ingest_guider_data.py --catalog-dataset-name monster_guide_catalog
```

> **Note**: Run the notebook from the `guider_roi_extras` directory so paths can find the `data` directory.

### 2. Test GuiderROIs

The `guider_roi_test.ipynb` notebook provides a complete workflow:

1. **Configuration** - Set target coordinates and paths
2. **Data Generation** - Create aligned test catalogs around target coordinates  
3. **Butler Ingestion** - Create repository with custom dataset names
4. **Testing** - Test both Butler-based and file-based GuiderROIs
5. **ROI Selection** - Guide star selection and configuration generation

Note: On the jupyterNb I run this notebook from the guider_roi_extra directory so paths
can find the data directory

## Example Usage

### From the Notebook
```python
from lsst.ts.observatory.control.utils.extras.guider_roi import GuiderROIs

# Butler-based mode
groi_butler = GuiderROIs(
    butler=butler,
    catalog_name="monster_guide_catalog",
    collection="monster_guide",
    nside=32
)

# File-based mode  
groi_file = GuiderROIs(
    butler=None,
    catalog_path="data/Monster_guide",
    vignetting_file="data/vignetting_vs_angle.npz",
    nside=32
)

# Test ROI selection workflow
test_roi_selection_workflow(groi_butler)  # or groi_file
```

### Summit Environment (BestEffortIsr)
```python
# Automatic BestEffortIsr usage (summit environment)
groi_summit = GuiderROIs(
    # BestEffortIsr will be used automatically if available
    catalog_name="operational_catalog_name",
    collection="operational_collection",
    nside=32
)

# Explicit BestEffortIsr usage
from lsst.summit.utils import BestEffortIsr
best_effort_isr = BestEffortIsr()
groi_summit = GuiderROIs(
    butler=best_effort_isr.butler,
    catalog_name="operational_catalog_name",
    collection="operational_collection",
    nside=32
)
```

### Command Line Data Generation
```bash
# Generate data around specific coordinates
python generate_test_guider_data.py \
    --target-ra 120.0 --target-dec -45.0 \
    --neighbor-radius 2 \
    --num-catalogs 50 --stars-per-catalog 75

# Ingest with custom dataset names
python ingest_guider_data.py \
    --repo-path data/my_repo \
    --collection my_collection \
    --catalog-dataset-name my_catalog_name
```

## Generated Data Structure

```
data/
├── Monster_guide/          # HEALPix catalog CSV files
│   ├── 10218.csv
│   ├── 10219.csv
│   └── ...
├── vignetting_vs_angle.npz # Vignetting correction data
└── monster_guide_repo/     # Butler repository
    └── ...
```