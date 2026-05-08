from dataclasses import dataclass
from functools import cache

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
    with open(DEFAULT_TAG_SELECTION_CSV, "r") as f:
        lines = f.readlines()
        if not lines:
            return []
        header = lines[0].strip().split("\t")
        assert header[:2] == ["name", "tag"]
        li = []
        for line in lines[1:]:
            fields = line.strip().split("\t")
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
