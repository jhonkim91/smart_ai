"""Obsidian vault -> Chroma 인덱서.

사람이 읽는 지식(Obsidian .md)을 기계가 검색하는 지식(Chroma 벡터)으로 동기화한다.
임베딩은 Ollama의 nomic-embed-text 사용 (전부 로컬/무료).

사용:
    python -m memory.index_vault            # 변경된 파일만 증분 인덱싱
    python -m memory.index_vault --full     # 전체 재인덱싱
"""
import argparse
import sys
from pathlib import Path

from hermes import bus
from hermes.config import CHROMA_PATH, OLLAMA_EMBED_MODEL, OLLAMA_HOST, VAULT_PATH

COLLECTION = "vault"
CHUNK_SIZE = 900  # 문자 기준. 한국어는 토큰 밀도가 높아 800~1000이 무난


def chunk_text(text: str, max_len: int = CHUNK_SIZE) -> list[str]:
    """빈 줄 기준 문단 병합 -> max_len 근처로 청크 분할."""
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        if len(cur) + len(p) + 2 <= max_len:
            cur = f"{cur}\n\n{p}" if cur else p
            continue
        if cur:
            chunks.append(cur)
        while len(p) > max_len:  # 비정상적으로 긴 문단은 강제 분할
            chunks.append(p[:max_len])
            p = p[max_len:]
        cur = p
    if cur:
        chunks.append(cur)
    return chunks


def _clients():
    import chromadb  # 지연 임포트 (무거운 의존성)
    import ollama

    chroma = chromadb.PersistentClient(path=str(CHROMA_PATH))
    col = chroma.get_or_create_collection(
        COLLECTION, metadata={"hnsw:space": "cosine"}
    )
    oll = ollama.Client(host=OLLAMA_HOST)
    return col, oll


def embed(oll, text: str) -> list[float]:
    return oll.embeddings(model=OLLAMA_EMBED_MODEL, prompt=text)["embedding"]


def _indexed_mtimes() -> dict[str, float]:
    with bus.conn() as c:
        rows = c.execute("SELECT path, mtime FROM vault_index").fetchall()
        return {r["path"]: r["mtime"] for r in rows}


def _remember(path: str, mtime: float) -> None:
    with bus.conn() as c:
        c.execute(
            "INSERT INTO vault_index (path, mtime) VALUES (?, ?) "
            "ON CONFLICT(path) DO UPDATE SET mtime = excluded.mtime",
            (path, mtime),
        )


def index(full: bool = False) -> None:
    bus.init_db()
    if not VAULT_PATH.exists():
        sys.exit(f"vault 경로 없음: {VAULT_PATH} (.env의 VAULT_PATH 확인)")

    col, oll = _clients()
    seen = {} if full else _indexed_mtimes()
    md_files = sorted(VAULT_PATH.rglob("*.md"))
    changed = 0

    for f in md_files:
        rel = str(f.relative_to(VAULT_PATH))
        mtime = f.stat().st_mtime
        if not full and seen.get(rel) == mtime:
            continue

        text = f.read_text(encoding="utf-8", errors="replace")
        chunks = chunk_text(text)
        # 기존 청크 제거 후 재삽입 (파일 단위 갱신)
        col.delete(where={"path": rel})
        if chunks:
            col.add(
                ids=[f"{rel}::{i}" for i in range(len(chunks))],
                embeddings=[embed(oll, c) for c in chunks],
                documents=chunks,
                metadatas=[{"path": rel, "chunk": i} for i in range(len(chunks))],
            )
        _remember(rel, mtime)
        changed += 1
        print(f"  ↻ {rel} ({len(chunks)} chunks)")

    print(f"완료: 파일 {len(md_files)}개 중 {changed}개 갱신 "
          f"(collection={COLLECTION}, path={CHROMA_PATH})")


def main() -> int:
    p = argparse.ArgumentParser(prog="memory.index_vault")
    p.add_argument("--full", action="store_true", help="전체 재인덱싱")
    args = p.parse_args()
    try:
        index(full=args.full)
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[index_vault] 실패: {e}", file=sys.stderr)
        print("Ollama 실행 여부와 임베딩 모델 설치 확인: "
              "ollama pull nomic-embed-text", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
