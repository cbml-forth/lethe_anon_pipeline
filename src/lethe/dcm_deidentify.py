import subprocess
import time
import xml.etree.ElementTree as etree
from collections import namedtuple
from hashlib import sha256
from pathlib import Path

from loguru import logger

from lethe.pseudo import PseudonymGenerator

from .defaults import DEFAULT_UIDROOT

CTPResults = namedtuple("CTPResults", ["elapsed_time", "processed_count"])


def _process_ctp_output(lines: list[str]) -> CTPResults:
    elapsed_time = 0
    processed_count = 0
    for line in lines:
        if line.startswith("Elapsed time:"):
            elapsed_time = float(line.strip().split(":")[1].strip())
        elif "Anonymized file" in line:
            processed_count += 1
    return CTPResults(elapsed_time, processed_count)


def run_ctp(
    *,
    input_dir: Path,
    output_dir: Path,
    anon_script: Path,
    site_id: str,
    pepper: str,
    threads: int,
    pseudonym_generator: PseudonymGenerator | None = None,
    verbose: bool = False
) -> None:
    # use the folder of the anon.script as the current working directory
    cwd = anon_script.parent

    # To make more difficult the identification of the original provider given
    # the contents of the anonymized DICOM files, we hash the "site id" and add
    # its hex digest as the "provider id" in the result DICOM images. We are using
    # SHA-256 which produces hex string of 32 x 2 = 64 bytes, so it's ok to add it
    # on any tag of "LO" (Long String) value representation (VR) that is at most 64
    # characters/bytes according to DICOM :
    # https://dicom.nema.org/dicom/2013/output/chtml/part05/sect_6.2.html#:~:text=LO
    #
    #
    providerId = sha256(site_id.encode()).hexdigest()

    cmd = [
        "java",
        "-jar",
        "DAT.jar",
        "-n",
        str(threads),
        "-pUIDROOT",
        DEFAULT_UIDROOT,
        "-pPROVIDERID",
        providerId,
        "-pSECRET_KEY",
        pepper,
        "-in",
        str(input_dir.absolute()),
        "-out",
        str(output_dir.absolute()),
    ]
    if pseudonym_generator is not None:  # YOLO, pseudonymize!!
        # Create the Lookup Table (lut) to be given to CTP:
        ctp_lut = output_dir / "__patient_id_lookup_table.txt"
        with open(ctp_lut, "w") as fp:
            ctp_type: str = "ptid"
            for k, v in pseudonym_generator.to_dict().items():
                fp.write(f"{ctp_type}/{k} = {v}\n")
        cmd.extend(["-lut", str(ctp_lut)])

        # Make sure that the CTP script has the @lookup command for PatientID:
        tree = etree.parse(anon_script)
        patient_id_element = tree.find('e[@t="00100020"]')
        patient_name_element = tree.find('e[@t="00100010"]')
        pseudo_directive = "@lookup(this,ptid)"
        if patient_id_element is not None:
            # Updating CTP script to use @lookup for PatientID:
            patient_id_element.text = pseudo_directive
            # and also for PatientName:
            patient_name_element.text = f"{pseudo_directive}@param(^Anonymous)"
            anon_script = output_dir / "__anon.script"
            tree.write(
                anon_script,
                xml_declaration=False,
                encoding="UTF-8",
                short_empty_elements=False,
            )

    cmd.extend(["-da", str(anon_script)])

    if verbose:
        cmd.append("-v")

    log_file = output_dir / ("ctp-" + time.strftime("%Y%m%d-%H%M%S"))
    stdout = log_file.with_name(log_file.name + ".out").open("w+")
    stderr = log_file.with_name(log_file.name + ".err").open("w+")

    logger.info("Running CTP command, output will be saved to {}".format(output_dir))
    logger.info("CTP standard output and error will be saved to {}".format(log_file))
    process = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, cwd=cwd)
    retcode = process.wait()
    stdout.flush()
    stderr.flush()
    stdout.seek(0)
    stderr.seek(0)
    results = _process_ctp_output(stdout.readlines())
    for line in stderr.readlines():
        print(f"CTP ERROR: {line}")
    logger.info(
        "CTP command completed, elapsed time: {} seconds, files anonymized: {}".format(
            results.elapsed_time, results.processed_count
        )
    )
    stdout.close()
    stderr.close()
