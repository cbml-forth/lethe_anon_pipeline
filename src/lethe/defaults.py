from pathlib import Path

DEFAULT_UIDROOT = "1.3.6.1.4.1.58108.2023"
DEFAULT_PATIENT_ID_PREFIX = "EUCAIM-"
DEFAULT_IGNORE_CSV_PREFIX = "_"
DEFAULT_STUDIES_METADATA_CSV = "dcm_studies_metadata.csv"
DEFAULT_SERIES_METADATA_CSV = "dcm_series_metadata.csv"
DEFAULT_TAG_SELECTION_CSV = Path(__file__).parent.parent.parent / "tag_selection.csv"
DEFAULT_CPU_THREADS = 10
DEFAULT_STATE_DIR = Path(__file__).parent.parent.parent / "db"
