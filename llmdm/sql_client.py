import json
import logging
import os
import sqlite3
from typing import Optional

from llmdm.location import Location
from llmdm.npc import NPC
from llmdm.utils import SAVE_DIR

logger = logging.getLogger(__name__)


class SQLClient:
    def __init__(self, db_name):
        if not os.path.exists(SAVE_DIR):
            os.mkdir(SAVE_DIR)
        self.conn = sqlite3.connect(os.path.join(SAVE_DIR, f"{db_name}.sql"))
        # Enable foreign key constraints
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        # Create the places table
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS places (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            )
        """
        )
        # Create the game_state table
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS game_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                date TEXT,
                location INTEGER,
                mode TEXT,
                FOREIGN KEY (location) REFERENCES places(id)
            )
        """
        )
        # Ensure there's only one row in game_state (id=1)
        self.cursor.execute("INSERT OR IGNORE INTO game_state (id) VALUES (1)")

        # create the locations table
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS locations (
                name TEXT PRIMARY KEY,
                description TEXT,
                connections TEXT,
                npcs TEXT,
                parent_location TEXT,
                sublocations TEXT
            )
        """
        )
        # Create the npcs table if it doesn't exist.
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS npcs (
                name TEXT PRIMARY KEY,
                description TEXT,
                location_name TEXT,
                behavior_type TEXT,
                bonds TEXT,
                ideals TEXT,
                flaws TEXT
            )
        """
        )
        self.conn.commit()

    def get_game_state(self):
        self.cursor.execute("SELECT date, location, mode FROM game_state WHERE id = 1")
        row = self.cursor.fetchone()
        if row:
            return {"date": row[0], "location": row[1], "mode": row[2]}
        else:
            return None

    def set_game_state(self, **kwargs):
        # Build the query dynamically
        columns = ", ".join(kwargs.keys())
        placeholders = ", ".join("?" * len(kwargs))
        values = list(kwargs.values())
        # Ensure id=1
        self.cursor.execute(
            f"""
            INSERT OR REPLACE INTO game_state (id, {columns})
            VALUES (1, {placeholders})
        """,
            (values,),
        )
        self.conn.commit()

    def update_game_state(self, **kwargs):
        # Build the query dynamically
        assignments = ", ".join([f"{key}=?" for key in kwargs.keys()])
        values = list(kwargs.values())
        # Ensure id=1
        self.cursor.execute(
            f"""
            UPDATE game_state
            SET {assignments}
            WHERE id = 1
        """,
            (values,),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()

    def save_location(self, location: Location):
        connections = json.dumps(location.connections)
        npcs = json.dumps([npc.name for npc in location.npcs])
        sublocations = json.dumps([loc.name for loc in location.sublocations])

        self.cursor.execute(
            """
            INSERT OR REPLACE INTO locations (
                name, description, connections, npcs, parent_location, sublocations
            ) VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                location.name,
                location.description,
                connections,
                npcs,
                location.parent_location,
                sublocations,
            ),
        )
        self.conn.commit()
        logger.debug(f"Location '{location.name}' saved to the database.")

    def get_location(self, name: str) -> Optional[Location]:
        self.cursor.execute(
            "SELECT * FROM locations WHERE name = ?",
            (name,),
        )
        row = self.cursor.fetchone()
        if row:
            (
                name,
                description,
                connections,
                npcs,
                parent_location,
                sublocations,
            ) = row
            location = Location(
                name=name,
                description=description,
                connections=json.loads(connections),
                npcs=json.loads(npcs),
                parent_location=parent_location,
                sublocations=json.loads(sublocations),
            )
            logger.debug(f"Location '{name}' loaded from the database.")
            return location
        else:
            logger.debug(f"Location '{name}' not found in the database.")
            return None

    def save_npc(self, npc: NPC):
        """Save or update an NPC instance in the database."""
        self.cursor.execute(
            """
            INSERT OR REPLACE INTO npcs (
                name, description,
                location_name, behavior_type,
                bonds, ideals, flaws
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                npc.name,
                npc.description,
                npc.location_name,
                npc.behavior_type,
                npc.bonds,
                npc.ideals,
                npc.flaws,
            ),
        )
        self.conn.commit()
        logger.debug(f"NPC '{npc.name}' saved to the database.")

    def get_npc(self, name: str) -> Optional[NPC]:
        """Retrieve an NPC instance from the database by name."""
        self.cursor.execute(
            "SELECT * FROM npcs WHERE name = ?",
            (name,),
        )
        row = self.cursor.fetchone()
        if row:
            npc = NPC(*row)
            logger.debug(f"NPC '{name}' loaded from the database.")
            return npc
        else:
            logger.debug(f"NPC '{name}' not found in the database.")
            return None
