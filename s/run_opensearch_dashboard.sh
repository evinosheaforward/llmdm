#!/bin/bash

out=$(
    podman run -d --name opensearch-dashboards \
    -e "OPENSEARCH_HOSTS=http://localhost:9200" \
    -p 5601:5601 \
    opensearchproject/opensearch-dashboards:latest
)

if [[ "$out" == "Error:"* ]]; then
    podman start opensearch-dashboards
fi

podman ps
