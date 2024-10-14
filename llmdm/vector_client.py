from opensearchpy import OpenSearch
from opensearchpy.exceptions import RequestError


class OpenSearchClient:
    def __init__(self, save_name, host="localhost", port=9200):
        self.client = OpenSearch(
            hosts=[{"host": host, "port": port}],
            http_compress=True,  # Enables gzip compression for request bodies
        )
        self.index_name = save_name
        self.create_index()

    def create_index(self):
        try:
            response = self.client.indices.create(index=self.index_name)
            return response
        except RequestError as e:
            if "resource_already_exists_exception" not in str(e):
                raise e

    def index_document(self, document, doc_id=None):
        return self.client.index(index=self.index_name, body=document, id=doc_id)

    def search_documents(self, query):
        return self.client.search(index=self.index_name, body=query)


if __name__ == "__main__":
    client = OpenSearchClient()

    # Create an index
    index_body = {
        "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}}
    }
    client.create_index(index_name="my_index", body=index_body)

    # Index a document
    document = {"title": "Test document", "content": "This is a test document."}
    client.index_document(index_name="my_index", document=document)

    # Search for a document
    search_query = {"query": {"match": {"content": "test"}}}
    search_results = client.search_documents(index_name="my_index", query=search_query)
    print(search_results)
