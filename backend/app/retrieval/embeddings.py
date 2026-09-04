from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors


@dataclass(frozen=True)
class Neighbor:
    identifier: str
    score: float


class EmbeddingIndex:
    """FAISS index when available, bounded TF-IDF neighbors otherwise."""

    def __init__(self, model_name: str, prefer_transformer: bool = True) -> None:
        self.model_name = model_name
        self.prefer_transformer = prefer_transformer
        self.identifiers: list[str] = []
        self.backend = "uninitialized"
        self._vectors: object | None = None
        self._index: object | None = None
        self._encoder: object | None = None
        self._vectorizer: TfidfVectorizer | None = None

    def fit(self, identifiers: list[str], texts: list[str]) -> "EmbeddingIndex":
        self.identifiers = identifiers
        safe_texts = [text if text.strip() else "unknown maintenance record" for text in texts]
        if self.prefer_transformer and self._fit_faiss(safe_texts):
            return self
        self._vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=4096, min_df=1)
        vectors = self._vectorizer.fit_transform(safe_texts)
        neighbors = NearestNeighbors(metric="cosine", algorithm="brute")
        neighbors.fit(vectors)
        self._vectors = vectors
        self._index = neighbors
        self.backend = "tfidf-nearest-neighbors"
        return self

    def similarities_for_pairs(self, pairs: list[tuple[str, str]]) -> dict[tuple[str, str], float]:
        if not pairs or self._vectors is None:
            return {}
        positions = {identifier: index for index, identifier in enumerate(self.identifiers)}
        valid_pairs = [pair for pair in pairs if pair[0] in positions and pair[1] in positions]
        left = [positions[pair[0]] for pair in valid_pairs]
        right = [positions[pair[1]] for pair in valid_pairs]
        if self.backend == "sentence-transformers-faiss":
            scores = np.sum(self._vectors[left] * self._vectors[right], axis=1)
        else:
            scores = np.asarray(
                self._vectors[left].multiply(self._vectors[right]).sum(axis=1)
            ).reshape(-1)
        return {
            pair: float(max(0, min(1, score)))
            for pair, score in zip(valid_pairs, scores, strict=True)
        }

    def query(self, text: str, top_k: int = 10) -> list[Neighbor]:
        if not self.identifiers or self._index is None:
            return []
        count = min(top_k, len(self.identifiers))
        if self.backend == "sentence-transformers-faiss":
            vector = self._encoder.encode([text], normalize_embeddings=True).astype("float32")
            scores, indices = self._index.search(vector, count)
            pairs = zip(indices[0], scores[0], strict=True)
        else:
            vector = self._vectorizer.transform([text])
            distances, indices = self._index.kneighbors(vector, n_neighbors=count)
            pairs = (
                (item, 1 - distance)
                for item, distance in zip(indices[0], distances[0], strict=True)
            )
        return [
            Neighbor(self.identifiers[item_index], float(max(0, min(1, score))))
            for item_index, score in pairs
        ]

    def _fit_faiss(self, texts: list[str]) -> bool:
        try:
            import faiss
            from sentence_transformers import SentenceTransformer
        except ImportError:
            return False
        encoder = SentenceTransformer(self.model_name)
        vectors = np.asarray(encoder.encode(texts, normalize_embeddings=True), dtype="float32")
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        self._encoder = encoder
        self._vectors = vectors
        self._index = index
        self.backend = "sentence-transformers-faiss"
        return True
