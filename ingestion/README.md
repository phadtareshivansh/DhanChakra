# Dhan-Chakra — Ingestion Layer

This layer handles data ingestion from MCA CSV, GST CSV, and synthetic datasets.

## Scripts

- `mca_loader.py` — Loads MCA company master data CSV into Neo4j
- `gst_loader.py` — Loads GST returns CSV into Neo4j
- `amlworld_loader.py` — Loads IBM AMLworld/AMLSim synthetic data

## Usage

```bash
# From within the ingestion container
python scripts/mca_loader.py --file /data/mca_sample.csv
```