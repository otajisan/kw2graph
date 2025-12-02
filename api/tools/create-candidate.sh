#!/bin/bash

curl -i -XGET \
  -H 'content-type: application/json' \
  localhost:8000/candidate -d '{
    "index": "videos", "field": "snippet.title", "keyword": "料理"
}'
