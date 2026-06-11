"""vault RAG 검색. Hermes/서브에이전트가 과거 결정·런북을 조회하는 진입점.

사용:
    python -m memory.search "KIS API rate limit 정책"
    python -m memory.search "쇼츠 업로드 절차" -k 3
"""
import argparse
import sys

from memory.index_vault import COLLECTION, _clients, embed


def search(query: str, k: int = 5) -> list[dict]:
    col, oll = _clients()
    res = col.query(query_embeddings=[embed(oll, query)], n_results=k)
    out = []
    for doc, meta, dist in zip(
        res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        out.append({"path": meta["path"], "chunk": meta["chunk"],
                    "distance": round(dist, 4), "text": doc})
    return out


def main() -> int:
    p = argparse.ArgumentParser(prog="memory.search")
    p.add_argument("query")
    p.add_argument("-k", type=int, default=5, help="결과 개수")
    args = p.parse_args()
    try:
        hits = search(args.query, args.k)
    except Exception as e:  # noqa: BLE001
        print(f"[search] 실패: {e}", file=sys.stderr)
        print("먼저 인덱싱: python -m memory.index_vault", file=sys.stderr)
        return 1
    if not hits:
        print("결과 없음. 인덱싱 여부 확인: python -m memory.index_vault")
        return 0
    for h in hits:
        print(f"\n── {h['path']} (chunk {h['chunk']}, dist {h['distance']}) ──")
        print(h["text"][:600])
    return 0


if __name__ == "__main__":
    sys.exit(main())
