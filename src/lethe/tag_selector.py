from dataclasses import dataclass
from functools import cache

import clevercsv
from pydicom.datadict import get_entry
from pydicom.tag import BaseTag, Tag

from lethe.defaults import DEFAULT_TAG_SELECTION_CSV


@dataclass(frozen=True, slots=True)
class TagDescription:
    name: str
    tag: BaseTag
    vr: str
    vm: str

    def is_multivalued(self) -> bool:
        return self.vm != "1"

    def is_numeric(self) -> bool:
        return self.vr in ["DS", "IS", "AS", "FL", "FD", "UN"]


@cache
def tags_to_select() -> list[TagDescription]:
    li = []
    with open(DEFAULT_TAG_SELECTION_CSV, "r") as fp:
        dialect = clevercsv.Sniffer().sniff(fp.read(1000))
        if dialect is None:
            return []
        fp.seek(0)
        reader = clevercsv.reader(fp, dialect)
        lines: list[list[str]] = list(reader)

        if not lines:
            return []
        header = lines[0]
        assert header[:2] == ["name", "tag"]
        for fields in lines[1:]:
            assert len(fields) >= 2
            name, tag = fields[:2]

            # tag will be something like this : (0008,0068)
            # we need to transform that to a tuple of ints where each element is an int decoded from the hex string
            # for example, (0008,0068) becomes (8, 104)
            tag_tup = tuple(
                int(x, 16)
                for x in tag.strip("()").split(
                    ",",
                    maxsplit=1,
                )
            )[:2]
            # get_entry returns the (VR, VM, name, is_retired, keyword) from the DICOM dictionary.
            vr, vm, _, _, _ = get_entry(tag_tup)
            li.append(TagDescription(name, Tag(tag_tup), vr, vm))
    return li
