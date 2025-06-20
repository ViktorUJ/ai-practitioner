#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Инкрементальная загрузка коллекции Minneapolis Institute of Art в ChromaDB.

Особенности:
- Клонирование/обновление репозитория artsmia/collection
- Проверка новых коммитов: пропуск, если репозиторий не изменился
- Выбор изменённых JSON через git diff между коммитами
- Хранение хешей JSON в коллекции ChromaDB (`filehash_collection`)
- Коллекции:
    - `mia_collection` – чанки документов
    - `commit_collection` – история коммитов
    - `filehash_collection` – хеши JSON-файлов

Запуск:
    chmod +x load_json.py
    ./load_json.py

Зависимости:
    python3 -m venv venv
    source venv/bin/activate
    pip install chromadb sentence-transformers tiktoken tqdm
"""
import os
import json
import subprocess
import hashlib
from typing import List, Dict, Any

# Прогресс-бар (fallback)
try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda x, **kwargs: x

# ChromaDB HTTP-клиент
import chromadb
from chromadb import HttpClient
from chromadb.config import Settings, DEFAULT_TENANT, DEFAULT_DATABASE
from sentence_transformers import SentenceTransformer
import tiktoken

# Конфигурация
ARTSMIA_REPO_URL = "https://github.com/artsmia/collection.git"
ARTSMIA_LOCAL_PATH = "./collection"
ARTSMIA_JSON_PATH = os.path.join(ARTSMIA_LOCAL_PATH, "objects")

CHUNK_COLLECTION = "mia_collection"
COMMIT_COLLECTION = "commit_collection"
FILEHASH_COLLECTION = "filehash_collection"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Инициализация
encoding = tiktoken.get_encoding("cl100k_base")
embedder = SentenceTransformer(EMBEDDING_MODEL)
client = HttpClient(
    host="localhost", port=8000, ssl=False,
    settings=Settings(), tenant=DEFAULT_TENANT, database=DEFAULT_DATABASE
)
chunk_collection = client.get_or_create_collection(CHUNK_COLLECTION)
commit_collection = client.get_or_create_collection(COMMIT_COLLECTION)
filehash_collection = client.get_or_create_collection(FILEHASH_COLLECTION)

# Вспомогательные функции
def run_git(args: List[str], cwd: str) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True).strip()

def get_current_commit(path: str) -> str:
    return run_git(["git", "rev-parse", "HEAD"], path)

def get_changed_files(last: str, current: str) -> List[str]:
    """Получить список добавленных/изменённых JSON между коммитами."""
    diff = run_git([
        "git", "diff", "--diff-filter=AM", "--name-only",
        last, current
    ], ARTSMIA_LOCAL_PATH)
    return [f for f in diff.splitlines() if f.endswith('.json')]

def hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def read_hashes_from_db() -> Dict[str, str]:
    """Загрузить сохранённые хеши JSON из filehash_collection."""
    result = {}
    resp = filehash_collection.get()
    ids = resp.get('ids', getattr(resp, 'ids', []))
    metas = resp.get('metadatas', getattr(resp, 'metadatas', []))
    for idx, fid in enumerate(ids):
        result[fid] = metas[idx].get('hash', '')
    return result

# Обработка изменённых документов
def process_changed_docs(changed: List[str]):
    """Обработать JSON-файлы, обновить хеши и вставить чанки."""
    fh_ids, fh_embs, fh_docs, fh_metas = [], [], [], []
    docs_to_embed: List[Dict[str, Any]] = []

    # Сбор хешей и подготовка документов
    for rel in tqdm(changed, desc="Processing JSON files", unit="file"):
        abs_path = os.path.join(ARTSMIA_LOCAL_PATH, rel)
        try:
            h = hash_file(abs_path)
        except Exception:
            continue
        fh_ids.append(rel)
        fh_embs.append(embedder.encode(h).tolist())
        fh_docs.append(h)
        fh_metas.append({'hash': h})

        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        parts = []
        for key in ['title','description','text','artist','culture','medium','creditline']:
            val = data.get(key)
            if val:
                parts.append(f"{key.capitalize()}: {val}")
        content = "\n".join(parts)
        if content:
            doc_id = data.get('id', rel)
            docs_to_embed.append({'id': doc_id, 'text': content})

    # Upserting file hashes батчами
    if fh_ids:
        max_batch = filehash_collection.get_max_batch_size()
        print(f"Upserting {len(fh_ids)} file hashes in batches of {max_batch}...")
        for start in tqdm(range(0, len(fh_ids), max_batch), desc="Upserting file hashes", unit="batch"):
            end = min(start + max_batch, len(fh_ids))
            filehash_collection.add(
                ids=fh_ids[start:end],
                embeddings=fh_embs[start:end],
                documents=fh_docs[start:end],
                metadatas=fh_metas[start:end]
            )

    # Эмбеддинг чанков
    if docs_to_embed:
        print(f"Embedding and storing {len(docs_to_embed)} docs...")
        for doc in tqdm(docs_to_embed, desc="Embedding docs", unit="doc"):
            tokens = encoding.encode(doc['text'])
            step = CHUNK_SIZE - CHUNK_OVERLAP
            chunks = [encoding.decode(tokens[i:i+CHUNK_SIZE]) for i in range(0, len(tokens), step)]
            ids2, embs2, texts2, metas2 = [], [], [], []
            for idx, chunk in enumerate(chunks):
                ids2.append(f"{doc['id']}_chunk_{idx}")
                embs2.append(embedder.encode(chunk).tolist())
                texts2.append(chunk)
                metas2.append({'source_id': doc['id'], 'chunk_index': idx})
            chunk_collection.add(
                ids=ids2,
                embeddings=embs2,
                documents=texts2,
                metadatas=metas2
            )

# Основная логика
if __name__ == '__main__':
    # Клонирование или обновление репозитория
    if not os.path.exists(ARTSMIA_LOCAL_PATH):
        subprocess.run(["git", "clone", ARTSMIA_REPO_URL, ARTSMIA_LOCAL_PATH], check=True)
    else:
        subprocess.run(["git", "-C", ARTSMIA_LOCAL_PATH, "pull"], check=True)

    # Получение текущего и последнего коммита
    curr = get_current_commit(ARTSMIA_LOCAL_PATH)
    resp = commit_collection.get()
    commit_ids = resp.get('ids', getattr(resp, 'ids', []))
    last = commit_ids[0] if commit_ids else ''

    if curr == last:
        print("No new commit, exiting.")
        exit(0)
    print(f"New commit detected: {curr}")
    commit_collection.add(
        ids=[curr],
        embeddings=[embedder.encode(curr).tolist()],
        documents=[f"Commit: {curr}"],
        metadatas=[{'commit': curr}]
    )

    # Определение списка файлов для обработки
    if not last:
        changed = []
        for root, _, files in os.walk(ARTSMIA_JSON_PATH):
            for f in files:
                if f.lower().endswith('.json'):
                    changed.append(os.path.relpath(os.path.join(root, f), ARTSMIA_LOCAL_PATH))
    else:
        changed = get_changed_files(last, curr)

    print(f"Processing {len(changed)} JSON files...")
    if changed:
        process_changed_docs(changed)
    else:
        print("No JSON changes detected.")

    print("Done.")
