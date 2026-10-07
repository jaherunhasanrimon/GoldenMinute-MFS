"""Embedding store interface and implementation for GNN representations.

Provides point-in-time lookups for wallet mule scores and structural embeddings (ARCHITECTURE.md Section 8 & Phase 1).
Supports In-Memory and Parquet backends (Redis backend ready for Phase 4).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("goldenminutes.models.embedding_store")


class EmbeddingStore(ABC):
    """Abstract interface for point-in-time GNN embedding and score lookups."""

    @abstractmethod
    def get_wallet_mule_score(self, day: int, wallet_id: str) -> float:
        """Return mule probability for wallet on given day offset."""
        pass

    @abstractmethod
    def get_wallet_embedding(self, day: int, wallet_id: str) -> np.ndarray:
        """Return 4-dim embedding vector for wallet on given day offset."""
        pass

    @abstractmethod
    def get_transaction_gnn_features(
        self, day: int, recipient_wallet_id: Optional[str], sender_wallet_id: Optional[str]
    ) -> Dict[str, float]:
        """Return dictionary of 6 GNN features for a transaction on day."""
        pass


class InMemoryEmbeddingStore(EmbeddingStore):
    """In-memory point-in-time embedding store backed by daily lookups."""

    def __init__(self, emb_dim: int = 4) -> None:
        self.emb_dim = emb_dim
        # Key: (day, wallet_id) -> score
        self.scores: Dict[Tuple[int, str], float] = {}
        # Key: (day, wallet_id) -> np.ndarray (shape: emb_dim)
        self.embeddings: Dict[Tuple[int, str], np.ndarray] = {}
        self.default_score: float = 0.0
        self.default_embedding: np.ndarray = np.zeros(emb_dim, dtype=np.float32)

    def set_wallet_record(self, day: int, wallet_id: str, score: float, embedding: np.ndarray) -> None:
        """Record score and embedding for a wallet on a specific snapshot day."""
        self.scores[(int(day), str(wallet_id))] = float(score)
        emb = np.asarray(embedding, dtype=np.float32)
        if emb.shape[0] != self.emb_dim:
            raise ValueError(f"Expected embedding dimension {self.emb_dim}, got {emb.shape[0]}")
        self.embeddings[(int(day), str(wallet_id))] = emb

    def get_wallet_mule_score(self, day: int, wallet_id: str) -> float:
        """Return mule probability for wallet on given day offset (0.0 if unseen)."""
        return self.scores.get((int(day), str(wallet_id)), self.default_score)

    def get_wallet_embedding(self, day: int, wallet_id: str) -> np.ndarray:
        """Return embedding vector for wallet on given day offset (zeros if unseen)."""
        return self.embeddings.get((int(day), str(wallet_id)), self.default_embedding)

    def get_transaction_gnn_features(
        self, day: int, recipient_wallet_id: Optional[str], sender_wallet_id: Optional[str]
    ) -> Dict[str, float]:
        """Return dictionary of 6 GNN features for a transaction on day."""
        rec_score = self.get_wallet_mule_score(day, recipient_wallet_id) if recipient_wallet_id else self.default_score
        snd_score = self.get_wallet_mule_score(day, sender_wallet_id) if sender_wallet_id else self.default_score

        rec_emb = self.get_wallet_embedding(day, recipient_wallet_id) if recipient_wallet_id else self.default_embedding

        return {
            "gnn_recipient_mule_score": float(rec_score),
            "gnn_sender_mule_score": float(snd_score),
            "gnn_recipient_emb_0": float(rec_emb[0]),
            "gnn_recipient_emb_1": float(rec_emb[1]),
            "gnn_recipient_emb_2": float(rec_emb[2]),
            "gnn_recipient_emb_3": float(rec_emb[3]),
        }

    def save(self, path: Path | str) -> None:
        """Persist embeddings and scores to a Parquet file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        rows = []
        for (day, w_id), score in self.scores.items():
            emb = self.embeddings.get((day, w_id), self.default_embedding)
            row = {
                "day": int(day),
                "wallet_id": str(w_id),
                "mule_score": float(score),
            }
            for i in range(self.emb_dim):
                row[f"emb_{i}"] = float(emb[i])
            rows.append(row)

        if rows:
            df = pd.DataFrame(rows)
        else:
            cols = ["day", "wallet_id", "mule_score"] + [f"emb_{i}" for i in range(self.emb_dim)]
            df = pd.DataFrame(columns=cols)

        df.to_parquet(p, index=False)
        logger.info(f"Saved {len(df)} embedding records to {p}")

    @classmethod
    def load(cls, path: Path | str, emb_dim: int = 4) -> InMemoryEmbeddingStore:
        """Load embeddings and scores from a Parquet file."""
        p = Path(path)
        store = cls(emb_dim=emb_dim)
        if not p.exists():
            logger.warning(f"Embedding file {p} does not exist; returning empty store.")
            return store

        df = pd.read_parquet(p)
        for _, row in df.iterrows():
            day = int(row["day"])
            w_id = str(row["wallet_id"])
            score = float(row["mule_score"])
            emb = np.array([float(row[f"emb_{i}"]) for i in range(emb_dim)], dtype=np.float32)
            store.set_wallet_record(day, w_id, score, emb)

        logger.info(f"Loaded {len(store.scores)} embedding records from {p}")
        return store
