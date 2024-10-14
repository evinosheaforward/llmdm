from dataclasses import dataclass, field
from typing import Dict, List, Optional

from llmdm.character import Character


@dataclass
class Location:
    name: str = "<name>"
    description: str = "<description>"
    connections: Dict[str, "Location"] = field(default_factory=dict)
    npcs: List["Character"] = field(default_factory=list)
    parent_location: Optional[str] = None  # Name of the parent location
    sublocations: List[str] = field(default_factory=list)  # Names of sublocations
