from sklearn.feature_extraction.text import TfidfVectorizer


def mine_candidate_phrases(texts: list[str], limit: int = 30) -> list[dict[str, float | str]]:
    usable = [text for text in texts if len(text.split()) >= 3]
    if len(usable) < 2:
        return []
    vectorizer = TfidfVectorizer(
        ngram_range=(2, 3), stop_words="english", min_df=2, max_features=500
    )
    try:
        matrix = vectorizer.fit_transform(usable)
    except ValueError:
        return []
    scores = matrix.mean(axis=0).A1
    phrases = vectorizer.get_feature_names_out()
    ranked = sorted(zip(phrases, scores, strict=True), key=lambda item: item[1], reverse=True)
    return [{"phrase": phrase, "score": round(float(score), 4)} for phrase, score in ranked[:limit]]
