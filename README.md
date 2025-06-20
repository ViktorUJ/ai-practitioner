# ai-practitioner
## start stack
``` 
docker compose up

```
## stop stack
```
docker compose stop

```
## get collections list  from  chromadb

``` 
curl -s -X GET \
  "http://localhost:8000/api/v2/tenants/default_tenant/databases/default_database/collections" \
  -H "Accept: application/json" \
| jq

```

## create collection in chromadb

```
curl -s -X POST "http://localhost:8000/api/v2/tenants/default_tenant/databases/default_database/collections" \
     -H "Content-Type: application/json" \
     -d '{
           "name": "my_collection40",
           "metadata": {
             "description": "Тестовая коллекция"
           }
         }' 
``` 

## init python dependencies 
```
python3 -m venv venv
source venv/bin/activate


pip install chromadb sentence-transformers tiktoken tqdm

```
## load data to chromadb
``` 
./load_json.py

```
```
......
New commit detected: 793c36765f8f06d237b5a7143e4426bae0fff8f5
Limiting to 103224 files (100% of 103224)
Processing 103224 JSON files...
Processing JSON files: 100%|██████████████████████████████████████████████████| 103224/103224 [27:18<00:00, 63.01file/s]
Upserting 103224 file hashes in batches of 5000...
Upserting file hashes: 100%|█████████████████████████████████████████████████████████| 21/21 [01:00<00:00,  2.87s/batch]
Embedding and storing 103164 docs...
Embedding docs: 100%|████████████████████████████████████████████████████████| 103164/103164 [1:11:52<00:00, 23.92doc/s]
Done.

``` 
### check collection in chromadb
```
curl -s -X GET \
  "http://localhost:8000/api/v2/tenants/default_tenant/databases/default_database/collections" \
  -H "Accept: application/json" \
| jq

```

``` 
[
  {
    "id": "5aa3b12f-f91e-4ff4-8533-388aeb9ad89a",
    "name": "commit_collection",
    "configuration_json": {
      "hnsw": {
        "space": "l2",
        "ef_construction": 100,
        "ef_search": 100,
        "max_neighbors": 16,
        "resize_factor": 1.2,
        "sync_threshold": 1000
      },
      "spann": null,
      "embedding_function": {
        "type": "known",
        "name": "default",
        "config": {}
      }
    },
    "metadata": null,
    "dimension": 384,
    "tenant": "default_tenant",
    "database": "default_database",
    "log_position": 0,
    "version": 0
  },
  {
    "id": "9f53debc-09a8-4aa0-b48a-0953cdc2d900",
    "name": "mia_collection",
    "configuration_json": {
      "hnsw": {
        "space": "l2",
        "ef_construction": 100,
        "ef_search": 100,
        "max_neighbors": 16,
        "resize_factor": 1.2,
        "sync_threshold": 1000
      },
      "spann": null,
      "embedding_function": {
        "type": "known",
        "name": "default",
        "config": {}
      }
    },
    "metadata": null,
    "dimension": 384,
    "tenant": "default_tenant",
    "database": "default_database",
    "log_position": 0,
    "version": 0
  },
  {
    "id": "a284386b-0b50-4d76-9881-d7711e459d5a",
    "name": "filehash_collection",
    "configuration_json": {
      "hnsw": {
        "space": "l2",
        "ef_construction": 100,
        "ef_search": 100,
        "max_neighbors": 16,
        "resize_factor": 1.2,
        "sync_threshold": 1000
      },
      "spann": null,
      "embedding_function": {
        "type": "known",
        "name": "default",
        "config": {}
      }
    },
    "metadata": null,
    "dimension": 384,
    "tenant": "default_tenant",
    "database": "default_database",
    "log_position": 0,
    "version": 0
  }
]

```

## get count from db
``` 
curl  -X GET   "http://localhost:8000/api/v2/tenants/default_tenant/databases/default_database/collections/9f53debc-09a8-4aa0-b48a-0953cdc2d900/count"   -H "Accept: application/json" ; echo
```

``` 
99634
```

## start search service
```
./search_server.py

```
``` 
INFO:     Started server process [21357]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)

```
## test search service
```
curl -X POST http://localhost:8080/search      -H "Content-Type: application/json"      -d '{
           "query": "Show me American paintings from the 19th century",
           "top_k": 3
         }'  -s | jq
```

``` 
{
  "results": [
    {
      "chunk": "Title: Portrait of a Man\nArtist: artist: Unknown American, 19th century\nMedium: Oil on canvas on board\nCreditline: Gift of Charlotte Ordway",
      "metadata": {
        "chunk_index": 0,
        "source_id": "http://api.artsmia.org/objects/1795"
      },
      "distance": 0.6644769
    },
    {
      "chunk": "Title: Untitled\nArtist: Unknown American, 19th century\nMedium: Watercolor, pencil and ink on paper\nCreditline: Gift of Barbara and Edwin Braman",
      "metadata": {
        "source_id": 99493,
        "chunk_index": 0
      },
      "distance": 0.68005013
    },
    {
      "chunk": "Title: Portrait of a Woman\nArtist: artist: Unknown American, 19th century\nMedium: Oil on canvas on board\nCreditline: Gift of Charlotte Ordway",
      "metadata": {
        "chunk_index": 0,
        "source_id": "http://api.artsmia.org/objects/1796"
      },
      "distance": 0.70893407
    }
  ]
}

```
## before use bedrock **Amazon Nova Lite ** you need activate it in your AWS account

## documentation
`http://localhost:8080/docs`
or
`curl http://localhost:8080/openapi.json | jq`

## check 1
``` 
curl -X POST http://localhost:8080/ask   -H "Content-Type: application/json"   -d '{
    "query": "Find artworks with floral motifs or nature themes",
    "top_k": 5
  }' -s  | jq 

```
``` 
{
  "answer": "Based on the provided context, here are the artworks with floral motifs or nature themes:\n\n1. **Untitled (Floral Design)**\n   - **Artist:** Winold Reiss\n   - **Medium:** Gouache on board\n   - **Creditline:** The Modernism Collection, gift of Norwest Bank Minnesota\n\n2. **Paper Pattern in Floral Motif**\n   - **Artist:** Nancy Fisher Cyrette\n   - **Culture:** Anishinaabe (Ojibwe)\n   - **Medium:** Newsprint\n   - **Creditline:** Bequest from the Karen Daniels Petersen American Indian Collection\n\n3. **Paper Pattern in Floral Motif**\n   - **Artist:** Nancy Fisher Cyrette\n   - **Culture:** Anishinaabe (Ojibwe)\n   - **Medium:** Newsprint\n   - **Creditline:** Bequest from the Karen Daniels Petersen American Indian Collection\n\n4. **Handbook of Old Floral Patterns**\n   - **Publisher:** Imai Keitarō\n   - **Medium:** Woodblock print (nishiki-e), ink and color on paper\n   - **Creditline:** Gift of Sue Y.S. Kimm and Seymour Grufferman\n\n5. **[abstract floral forms]**\n   - **Artist:** Ushiku Kenji\n   - **Medium:** Ink and color on paper\n   - **Creditline:** Gift of Sue Y.S. Kimm and Seymour Grufferman\n\nAll these artworks feature floral motifs or nature themes.",
  "sources": [
    {
      "chunk_index": 0,
      "source_id": "http://api.artsmia.org/objects/8370"
    },
    {
      "chunk_index": 0,
      "source_id": 104458
    },
    {
      "chunk_index": 0,
      "source_id": 104460
    },
    {
      "chunk_index": 0,
      "source_id": 135871
    },
    {
      "chunk_index": 0,
      "source_id": 136027
    }
  ]
}
```

## check 2 (text output )
```
curl -X POST http://localhost:8080/ask   -H "Content-Type: application/json"   -d '{
    "query": "Find artworks with floral motifs or nature themes",
    "top_k": 5,    
    "response_type": "answer_only"
  }' -s
```
``` 
Based on the provided context, here are the artworks with floral motifs or nature themes:

1. **Untitled (Floral Design)**
   - **Artist:** Winold Reiss
   - **Medium:** Gouache on board
   - **Creditline:** The Modernism Collection, gift of Norwest Bank Minnesota

2. **Paper Pattern in Floral Motif**
   - **Artist:** Nancy Fisher Cyrette
   - **Culture:** Anishinaabe (Ojibwe)
   - **Medium:** Newsprint
   - **Creditline:** Bequest from the Karen Daniels Petersen American Indian Collection

3. **Paper Pattern in Floral Motif**
   - **Artist:** Nancy Fisher Cyrette
   - **Culture:** Anishinaabe (Ojibwe)
   - **Medium:** Newsprint
   - **Creditline:** Bequest from the Karen Daniels Petersen American Indian Collection

4. **Handbook of Old Floral Patterns**
   - **Publisher:** Imai Keitarō
   - **Medium:** Woodblock print (nishiki-e), ink and color on paper
   - **Creditline:** Gift of Sue Y.S. Kimm and Seymour Grufferman

5. **[abstract floral forms]**
   - **Artist:** Ushiku Kenji
   - **Medium:** Ink and color on paper
   - **Creditline:** Gift of Sue Y.S. Kimm and Seymour Grufferman

All these artworks feature floral motifs or nature themes.

```