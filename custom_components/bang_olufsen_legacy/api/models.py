from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LooseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ServiceEntry(LooseModel):
    name: str
    path: str


class ServicesResponse(LooseModel):
    services: list[ServiceEntry]


class Product(LooseModel):
    jid: str
    friendlyName: str | None = None


class Source(LooseModel):
    id: str | None = None
    friendlyName: str | None = None
    category: str | None = None
    profile: str | None = None
    borrowed: bool | None = None
    inUse: bool | None = None
    signalSensed: bool | None = None
    linkable: bool | None = None
    product: Product | None = None
    sourceType: dict[str, Any] | None = None
    links: dict[str, Any] | None = Field(default=None, alias="_links")


class SourcesResponse(LooseModel):
    sources: list[tuple[str, Source]]


class ActiveSources(LooseModel):
    primary: str | None = None
    secondary: str | None = None


class ActiveSourcesResponse(LooseModel):
    activeSources: ActiveSources | None = None
    primaryExperience: dict[str, Any] | None = None
    secondaryExperience: dict[str, Any] | None = None


class FeaturesResponse(LooseModel):
    features: list[str]


class ProductId(LooseModel):
    productType: str | int | None = None
    typeNumber: str | int
    itemNumber: str | int
    serialNumber: str | int


class Software(LooseModel):
    version: str
    softwareUpdateProductTypeId: int | None = None


class ProductFriendlyName(LooseModel):
    productFriendlyName: str


class DeviceProfile(LooseModel):
    name: str
    version: int
    links: dict[str, Any] | None = Field(default=None, alias="_links")


class BeoDevice(LooseModel):
    productId: ProductId
    productFamily: str | None = None
    productFriendlyName: ProductFriendlyName | None = None
    proxyMasterLinkType: str | None = None
    software: Software
    anonymousProductId: str | None = None
    profiles: list[DeviceProfile] = Field(default_factory=list)


class DeviceInfoResponse(LooseModel):
    beoDevice: BeoDevice


class LineInSettingsCapabilities(LooseModel):
    editable: list[str] = Field(default_factory=list)
    value: dict[str, Any] = Field(default_factory=dict)


class LineInSettings(LooseModel):
    sensitivity: str
    capabilities: LineInSettingsCapabilities | None = Field(default=None, alias="_capabilities")
    links: dict[str, Any] | None = Field(default=None, alias="_links")


class LineInSettingsProfile(LooseModel):
    name: str | None = None
    version: int | None = None
    links: dict[str, Any] | None = Field(default=None, alias="_links")
    lineInSettings: LineInSettings


class LineInSettingsProfileResponse(LooseModel):
    profile: LineInSettingsProfile


class VolumeRange(LooseModel):
    minimum: int
    maximum: int


class VolumeOutputState(LooseModel):
    level: int
    muted: bool
    range: VolumeRange | None = None


class VolumeState(LooseModel):
    speaker: VolumeOutputState
    headphone: VolumeOutputState | None = None


class VolumeLevel(LooseModel):
    level: int = Field(ge=0)


class VolumeMuted(LooseModel):
    muted: bool


class DeviceErrorBody(LooseModel):
    message: str
    type: str | None = None


class DeviceErrorResponse(LooseModel):
    error: DeviceErrorBody


class PlayQueueItem(LooseModel):
    id: str
    behaviour: str | None = None
    playOrder: str | None = None
    links: dict[str, Any] | None = Field(default=None, alias="_links")


class PlayQueueBody(LooseModel):
    id: str
    offset: int
    count: int
    startOffset: int
    total: int
    revision: int
    playNowId: str | None = None
    item: list[PlayQueueItem]
    links: dict[str, Any] | None = Field(default=None, alias="_links")


class PlayQueueResponse(LooseModel):
    playQueue: PlayQueueBody


class NotificationEnvelope(LooseModel):
    id: int | None = None
    timestamp: str | None = None
    type: str
    data: Any
