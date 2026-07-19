import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class FileManifest(BaseModel):
    """
    FileManifest tracks the cryptographic state, versioning, and conflict states 
    of a file in the Planetary Drive.
    """
    file_id: str = Field(..., description="Unique identifier for the file, typically a UUID or deterministic hash.")
    path: str = Field(..., description="Logical path in the drive.")
    
    # Cryptographic state
    content_hash: str = Field(..., description="Cryptographic hash of the file content.")
    hash_alg: str = Field(default="sha256", description="Algorithm used for the content_hash.")
    size_bytes: int = Field(..., description="Size of the file content in bytes.")
    
    # Versioning
    version: int = Field(default=1, description="Monotonically increasing version number.")
    vector_clock: Dict[str, int] = Field(default_factory=dict, description="Vector clock mapping node IDs to version counts.")
    last_modified: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), 
        description="Timestamp of the last modification."
    )
    is_deleted: bool = Field(default=False, description="Tombstone flag indicating if the file has been deleted.")
    
    # Conflict states
    is_conflict: bool = Field(default=False, description="True if the file is currently in a conflicted state.")
    conflict_bases: List[str] = Field(
        default_factory=list, 
        description="List of content hashes representing the base of the conflict."
    )
    conflict_variants: List[str] = Field(
        default_factory=list, 
        description="List of content hashes representing the conflicting variants."
    )

    def serialize(self) -> str:
        """Serializes the FileManifest to a JSON string."""
        return self.model_dump_json()

    @classmethod
    def deserialize(cls, data: str) -> "FileManifest":
        """Deserializes a JSON string to a FileManifest instance."""
        return cls.model_validate_json(data)
        
    def to_dict(self) -> dict:
        """Serializes the FileManifest to a dictionary."""
        return self.model_dump(mode='json')
        
    @classmethod
    def from_dict(cls, data: dict) -> "FileManifest":
        """Deserializes a dictionary to a FileManifest instance."""
        return cls.model_validate(data)
