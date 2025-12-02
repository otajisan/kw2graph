#!/bin/bash

curl -i -XPOST \
  -H 'content-type: application/json' \
  localhost:8000/candidate -d '{
    "index": "videos", "field": "snippet.title", "keyword": "料理"
}'
