"""
Copy from an input folder all dicom files to an output folder. In hte output folder the files
will be organized in a hierarchical structure based on the patient ID , study UID, and series UID.
"""

import shutil
from pathlib import Path

import clevercsv
from loguru import logger

from lethe.defaults import DEFAULT_SERIES_METADATA_CSV

from .dicom_utils import dcm_generator


def copy_and_organize(
    input_folder: Path,
    output_folder: Path,
    *,
    restructure: bool = True,
    extract_tags: bool = True,
):
    """Copy from an input folder all DICOM files to an output folder. If `restructure` is True, the files
    in the output folder will be organized in a hierarchical structure based on the patient ID, study UID,
    and series UID.
    """
    cnt = 0
    dirs: dict[str, int] = {}
    tags_extracted: dict[tuple[str, str, str], list[tuple[str, str]]] = {}
    # XXX: Should we order by InstanceNumber ??
    for dcm_info in dcm_generator(input_folder, extract_tags=extract_tags):
        current_output_folder = (
            (
                output_folder
                / dcm_info.patient_id
                / dcm_info.study_uid
                / dcm_info.series_uid
            )
            if restructure
            else output_folder / dcm_info.path.parent.relative_to(input_folder)
        )
        if extract_tags:
            tags_extracted[
                (dcm_info.patient_id, dcm_info.study_uid, dcm_info.series_uid)
            ] = dcm_info.tags
        if current_output_folder not in dirs:
            # Since we walk the input directory in top down manner, we are sure that when we visit
            # a directory its parent directory has already been visited and created. So
            # parents=True, exist_ok=True are not needed but ..ok :-)
            current_output_folder.mkdir(parents=True, exist_ok=True)
            dirs[current_output_folder] = 1
        index = dirs[current_output_folder]
        dirs[current_output_folder] += 1
        output_file = (
            current_output_folder / f"{index:05d}.dcm"
            if restructure
            else current_output_folder / dcm_info.path.name
        )
        shutil.copy(dcm_info.path, output_file)
        cnt += 1
    if extract_tags and tags_extracted:
        _export_extracted_tags(output_folder, tags_extracted)
    msg = "Copied and organized hierarchically" if restructure else "Copied"
    logger.info(f"{msg} {cnt} DICOM files")


def _export_extracted_tags(
    output_folder: Path,
    tags_extracted: dict[tuple[str, str, str], list[tuple[str, str]]],
) -> None:
    output_csv: Path = output_folder / DEFAULT_SERIES_METADATA_CSV
    num: int = 0
    with open(output_csv, "w") as fp_out:
        writer = clevercsv.writer(fp_out, "excel")
        first = next(iter(tags_extracted.values()))
        writer.writerow(
            [
                "PatientID",
                "StudyInstanceUID",
                "SeriesInstanceUID",
                *[tag_name for tag_name, _ in first],
            ]
        )
        for k, v in tags_extracted.items():
            patient_id, study_uid, series_uid = k
            writer.writerow(
                [patient_id, study_uid, series_uid, *[tag_val for _, tag_val in v]]
            )
            num += 1
    logger.info(f"Tag Extractor: Wrote {num} series metadata rows to {output_csv}")
