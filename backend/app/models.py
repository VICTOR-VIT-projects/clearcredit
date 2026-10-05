"""Claim schema 1.0 (see docs/CLAIM_SCHEMA.md) and API envelopes."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProjectType(str, Enum):
    avoided_deforestation = "avoided_deforestation"
    afforestation = "afforestation"
    other = "other"


class DataLabel(str, Enum):
    real = "real"                  # boundary from a published source (see data/README.md)
    illustrative = "illustrative"  # hand-built from public descriptions; not an official boundary
    synthetic = "synthetic"        # test case constructed for evaluation/demo


class Boundary(BaseModel):
    type: Literal["Polygon", "MultiPolygon"]
    coordinates: list[Any]


class Claim(BaseModel):
    """A carbon-credit claim. Everything except `submittedAt` is covered by the claim hash."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    schemaVersion: Literal["1.0"] = "1.0"
    projectId: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,64}$", description="Stable unique ID, e.g. VCS1115")
    developer: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$", description="Developer wallet address")
    projectType: ProjectType
    vintageYear: int = Field(ge=2000, le=2100)
    claimedCredits: int = Field(gt=0, le=2**53 - 1, description="Capped at 2^53-1 so JavaScript verifiers hash it exactly")
    creditUnit: Literal["tCO2e"] = "tCO2e"
    boundary: Boundary
    boundaryCrs: Literal["EPSG:4326"] = "EPSG:4326"
    sourceRegistry: str | None = Field(default=None, max_length=200, description="Registry name and external ID")
    boundarySource: str | None = Field(default=None, max_length=300, description="Where the boundary came from and how it was processed")
    dataLabel: DataLabel = Field(description="real | illustrative | synthetic — shown everywhere the claim is shown")
    submittedAt: str | None = Field(default=None, description="Server metadata; excluded from the hash")


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: Claim
    signature: str = Field(pattern=r"^0x[0-9a-fA-F]{130}$", description="Developer's EIP-712 signature over the Claim typed data")
