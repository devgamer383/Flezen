"""
Data structures and models for the Flezen API.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class FlezenFile:
    name: str
    size: int
    slug: str
    extension: Optional[str] = None
    visibility: str = "public"
    type: Optional[str] = None
    views: int = 0
    earnings: float = 0.0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlezenFile":
        return cls(
            name=data.get("name", ""),
            size=data.get("size", 0),
            slug=data.get("slug", ""),
            extension=data.get("extension"),
            visibility=data.get("visibility", "public"),
            type=data.get("type"),
            views=data.get("views", 0),
            earnings=float(data.get("earnings", 0.0)),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            raw=data,
        )

    @property
    def public_url(self) -> str:
        return f"https://flezen.com/s/{self.slug}"

    @property
    def intent_url(self) -> str:
        return (
            f"intent://flezen.com/s/{self.slug}#Intent;"
            f"scheme=flezen;package=com.devlooper.flezen;"
            f"S.browser_fallback_url=https://play.google.com/store/apps/details?id=com.devlooper.flezen;end"
        )


@dataclass
class StorageUsage:
    total_storage_used: int
    total_video_storage: int = 0
    total_audio_storage: int = 0
    total_image_storage: int = 0
    total_doc_storage: int = 0
    total_other_storage: int = 0
    raw: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StorageUsage":
        return cls(
            total_storage_used=data.get("total_storage_used", 0),
            total_video_storage=data.get("total_video_storage", 0),
            total_audio_storage=data.get("total_audio_storage", 0),
            total_image_storage=data.get("total_image_storage", 0),
            total_doc_storage=data.get("total_doc_storage", 0),
            total_other_storage=data.get("total_other_storage", 0),
            raw=data,
        )


@dataclass
class UploadInitResponse:
    signature: str
    signed_ids: List[str]
    part_size: int
    server_url: str
    raw: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UploadInitResponse":
        return cls(
            signature=data.get("signature", ""),
            signed_ids=data.get("signedIDs", []),
            part_size=data.get("partSize", 26214400),
            server_url=data.get("serverUrl", ""),
            raw=data,
        )
