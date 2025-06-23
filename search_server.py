#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTTP-сервер для RAG-пайплайна: поиск векторных чанков в ChromaDB,
генерация ответов через AWS Bedrock и кэширование в Redis.

Запуск:
    chmod +x search_server.py
    ./search_server.py

Зависимости:
    pip install fastapi uvicorn chromadb sentence-transformers boto3 tiktoken pydantic loguru redis

Endpoints:
- POST /search
    Возвращает чанки по запросу.
- POST /ask
    Выполняет поиск и генерацию ответа с опцией выдачи только текста или полного JSON и кэшированием.
"""
import os
import json
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, Body
from fastapi.openapi.utils import get_openapi
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from loguru import logger
import tiktoken
from sentence_transformers import SentenceTransformer
from chromadb import HttpClient
from chromadb.config import Settings, DEFAULT_TENANT, DEFAULT_DATABASE
import boto3
import botocore
import redis

# --------- Configuration ---------
CHROMA_HOST = os.getenv('CHROMA_HOST', 'localhost')
CHROMA_PORT = int(os.getenv('CHROMA_PORT', 8000))
CHROMA_SSL = False
TENANT = DEFAULT_TENANT
DATABASE = DEFAULT_DATABASE
COLLECTION_NAME = os.getenv('COLLECTION_NAME', 'mia_collection')

AWS_REGION = os.getenv('AWS_REGION', 'eu-north-1')
DEFAULT_MODEL_ID = 'amazon.nova-lite-v1:0'
TOP_K_DEFAULT = 5
MAX_TOKENS = 512
TEMPERATURE = 0.7
TOP_P = 0.9
CACHE_TTL = 30  # seconds

# --------- Init services ---------
app = FastAPI(
    title='RAG Search+LLM API',
    description='API для поиска и генерации ответов с использованием ChromaDB, AWS Bedrock и Redis-кэшем',
    version='1.0.0'
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes
    )
    app.openapi_schema = schema
    return app.openapi_schema
app.openapi = custom_openapi

# ChromaDB client
db_client = HttpClient(
    host=CHROMA_HOST, port=CHROMA_PORT, ssl=CHROMA_SSL,
    settings=Settings(), tenant=TENANT, database=DATABASE
)
collection = db_client.get_collection(COLLECTION_NAME)

# Embedding model
tokenizer = tiktoken.get_encoding('cl100k_base')
embedder = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

# Bedrock client
try:
    bedrock = boto3.client('bedrock-runtime', region_name=AWS_REGION)
except botocore.exceptions.NoRegionError:
    logger.error('AWS_REGION is not set')
    raise

# Redis client
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=0
)

# --------- Pydantic models ---------
class SearchRequest(BaseModel):
    query: str = Field(..., description='Текстовый запрос', example='Show me nature-themed artworks')
    top_k: int = Field(TOP_K_DEFAULT, ge=1, le=100, description='Кол-во чанков', example=5)

class Chunk(BaseModel):
    chunk: str
    metadata: Dict[str, Any]
    distance: float

class SearchResponse(BaseModel):
    results: List[Chunk]

class AskRequest(BaseModel):
    query: str = Field(..., description='Вопрос от пользователя', example='Find artworks with floral motifs or nature themes')
    top_k: int = Field(TOP_K_DEFAULT, ge=1, le=100, description='Кол-во чанков для контекста', example=5)
    model_id: str = Field(DEFAULT_MODEL_ID, description='Bedrock model ID', example='amazon.nova-lite-v1:0')
    response_type: str = Field('full', description='"full" или "answer_only"', example='answer_only')

class AskResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]
    cached: bool = False

# --------- Endpoints ---------
@app.post(
    '/search', response_model=SearchResponse,
    summary='Поиск векторами',
    description='Ищет релевантные векторные чанки по запросу.',
    tags=['search']
)
def search(req: SearchRequest = Body(...)):
    logger.info(f"Search request: {req.query}, top_k={req.top_k}")
    if not req.query.strip():
        raise HTTPException(400, 'Query must not be empty')
    embeddings = embedder.encode(req.query).tolist()
    try:
        resp = collection.query(
            query_embeddings=[embeddings],
            n_results=req.top_k,
            include=['documents', 'metadatas', 'distances']
        )
    except Exception as e:
        logger.error(f"ChromaDB error: {e}")
        raise HTTPException(500, str(e))
    docs, metas, dists = resp.get('documents', [[]])[0], resp.get('metadatas', [[]])[0], resp.get('distances', [[]])[0]
    results = [Chunk(chunk=d, metadata=m, distance=ds) for d, m, ds in zip(docs, metas, dists)]
    return SearchResponse(results=results)

@app.post(
    '/ask',
    summary='RAG + генерация',
    description='Поиск и генерация ответа через Nova Lite с кэшированием.',
    tags=['ask'],
)
def ask(req: AskRequest = Body(...)):
    cache_key = f"ask:{req.query}|{req.top_k}|{req.model_id}|{req.response_type}"
    cached = redis_client.get(cache_key)
    if cached:
        logger.info('Cache hit')
        text = cached.decode('utf-8')
        if req.response_type == 'answer_only':
            return PlainTextResponse(text, media_type='text/plain')
        data = json.loads(text)
        data['cached'] = True
        return data

    logger.info('Cache miss')
    # 1) Search
    search_resp = search(SearchRequest(query=req.query, top_k=req.top_k))
    if not search_resp.results:
        text = 'No docs found.\n\n'
        redis_client.setex(cache_key, CACHE_TTL, text)
        if req.response_type == 'answer_only':
            return PlainTextResponse(text, media_type='text/plain')
        return {'answer': 'No docs found.', 'sources': [], 'cached': False}

    # 2) Build context
    context = '\n---\n'.join([c.chunk for c in search_resp.results])
    sources = [c.metadata for c in search_resp.results]

    # 3) Invoke Bedrock
    payload = {
        'system': [{'text': 'You are a helpful assistant. Use only context.'}],
        'messages': [{'role': 'user', 'content': [{'text': f"Context:\n{context}\n\nQuestion: {req.query}"}]}],
        'inferenceConfig': {'maxTokens': MAX_TOKENS, 'temperature': TEMPERATURE, 'topP': TOP_P}
    }
    logger.debug(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
    try:
        resp = bedrock.invoke_model(
            modelId=req.model_id,
            body=json.dumps(payload),
            contentType='application/json',
            accept='application/json'
        )
    except Exception as e:
        logger.error(f"Bedrock invoke error: {e}")
        raise HTTPException(500, str(e))

    raw = resp['body'].read()
    logger.debug(f"Raw response: {raw.decode()}")
    result = json.loads(raw)
    if 'output' in result and 'message' in result['output']:
        answer = result['output']['message']['content'][0].get('text', '').strip()
    else:
        answer = result.get('completion', '').strip()

    # 4) Cache and return
    if req.response_type == 'answer_only':
        text = answer + "\n\n"
        redis_client.setex(cache_key, CACHE_TTL, text)
        return PlainTextResponse(text, media_type='text/plain')

    out = {'answer': answer, 'sources': sources, 'cached': False}
    redis_client.setex(cache_key, CACHE_TTL, json.dumps(out, ensure_ascii=False))
    return out

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8080)
