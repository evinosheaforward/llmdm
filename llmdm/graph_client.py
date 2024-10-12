from dataclasses import asdict

from arango import ArangoClient

from llmdm.data_types import Entity, Relation, data_type_from_str


class DatabaseWrapper:
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
        for collection_name in ["person", "place", "object"]:
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
                        "from_vertex_collections": ["person", "place", "object"],
                        "to_vertex_collections": ["person", "place", "object"],
                    }
                ],
            )
            print("Graph 'entity_graph' created.")
        else:
            print("Graph 'entity_graph' already exists.")

    def add_entity(self, entity: Entity):
        """Add a person to the database."""
        data = asdict(entity)
        data.update({"_key": entity.name.lower()})
        return self.db.collection(type(entity).__name__.lower()).insert(data)

    def add_relation(self, relation: Relation):
        """Create a relation between two entities."""
        self.db.graph(
            "entity_graph",
        ).edge_collection(
            "relation",
        ).insert(
            {k: v.lower() for k, v in asdict(relation).items() if v},
        )

    def get_entity_by_id(self, entity_id: str) -> Entity:
        """Get a specific entity by its document ID."""
        entity_id = entity_id.lower()
        collection_name = entity_id.split("/")[0]
        entity_type = data_type_from_str(collection_name)
        return entity_type(**self.db.collection(collection_name).get(entity_id))

    def get_relations_for_entity(self, entity: Entity):
        """Find all relations for a specific entity (either incoming or outgoing)."""
        return list(
            Relation(**datum)
            for datum in self.db.aql.execute(
                query="""
                    FOR edge IN relation
                        FILTER edge._from == @entity_id OR edge._to == @entity_id
                        RETURN edge
                """,
                bind_vars={
                    "entity_id": f"{type(entity).__name__}/{entity.name}".lower()
                },
            )
        )
