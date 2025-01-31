import logging
from dataclasses import dataclass

from arango import ArangoClient
from arango.exceptions import DocumentInsertError

from llmdm.utils import suppress_stdout

logger = logging.getLogger(__name__)


class GraphClient:
    def __init__(
        self,
        db_name,
        host="http://localhost:8529",
        username="root",
        password="password",
    ):
        self.db_name = db_name
        self.username = username
        self.password = password
        self.host = host
        with suppress_stdout():
            self.client = ArangoClient(hosts=host)
        self.db = self.get_db()
        self.setup_collections()

    def get_db(self):
        """Connect to the specified database, creating it if necessary."""
        sys_db = self.client.db(
            "_system", username=self.username, password=self.password
        )
        if not sys_db.has_database(self.db_name):
            sys_db.create_database(self.db_name)
        return self.client.db(
            self.db_name, username=self.username, password=self.password
        )

    def setup_collections(self):
        """Set up the necessary collections and graph."""
        COLLECTIONS = ["npc", "location", "quest", "object"]
        for collection_name in COLLECTIONS:
            if not self.db.has_collection(collection_name):
                self.db.create_collection(collection_name)

        if not self.db.has_collection("relation"):
            self.db.create_collection("relation", edge=True)

        if not self.db.has_graph("entity_graph"):
            self.db.create_graph(
                name="entity_graph",
                edge_definitions=[
                    {
                        "edge_collection": "relation",
                        "from_vertex_collections": COLLECTIONS,
                        "to_vertex_collections": COLLECTIONS,
                    }
                ],
            )
            logger.debug("Graph 'entity_graph' created.")
        else:
            logger.debug("Graph 'entity_graph' already exists.")

    def add_entity(self, entity: dataclass):
        """Add a person to the database."""
        data = {"name": entity.name, "_key": sanitize(entity.name)}
        logger.debug(f"DatabaseWrapper.add_entity - {data}")
        try:
            self.db.collection(sanitize(type(entity).__name__)).insert(data)
        except DocumentInsertError:
            logger.exception("Error adding entity")

    def add_relation(self, relation: dict):
        """Create a relation between two entities."""
        logger.debug(f"DatabaseWrapper.add_relation - {relation}")
        try:
            self.db.graph(
                "entity_graph",
            ).edge_collection(
                "relation",
            ).insert(
                {
                    k: "/".join(sanitize(i) for i in v.split("/"))
                    for k, v in relation.items()
                    if v
                },
            )
        except DocumentInsertError:
            logger.exception("Error adding relation")

    def get_relations_for_entity(self, entity: dataclass):
        """Find all relations for a specific entity (either incoming or outgoing)."""
        return self.db.aql.execute(
            query="""
                FOR edge IN relation
                    FILTER edge._from == @entity_id OR edge._to == @entity_id
                    RETURN edge
            """,
            bind_vars={
                "entity_id": f"{type(entity).__name__.lower()}/{sanitize(entity.name)}"
            },
        )


def sanitize(name):
    for token in "\"' ,-_/“”‘’":
        name = "".join(name.split(token)).lower()

    return name.lower()
