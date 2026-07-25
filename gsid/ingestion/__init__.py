"""Ingestion subsystem: modular source connectors + processing pipeline.

Note: `IngestionPipeline` is intentionally NOT imported here to avoid a circular
import (pipeline -> store -> ingestion.dedup). Import it directly:

    from gsid.ingestion.pipeline import IngestionPipeline
"""

from __future__ import annotations

from .connectors import FEED_REGISTRY, RssConnector, FeedItem

__all__ = ["FEED_REGISTRY", "RssConnector", "FeedItem"]
