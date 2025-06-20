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


```