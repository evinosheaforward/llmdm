import json
import logging
import os
import sqlite3
from dataclasses import asdict
from typing import Optional

from llmdm.location import Location
from llmdm.npc import NPC
from llmdm.quest import Quest
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
        # create the locations table
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS locations (
                name TEXT PRIMARY KEY,
                description TEXT,
                npcs TEXT,
                parent_location TEXT,
                sublocations TEXT,
                location_type TEXT,
                attributes TEXT
            )
        """
        )
        # # Create the game_state table
        # self.cursor.execute(
        #     """
        #     CREATE TABLE IF NOT EXISTS game_state (
        #         id INTEGER PRIMARY KEY CHECK (id = 1),
        #         date TEXT,
        #         location INTEGER,
        #         mode TEXT,
        #         FOREIGN KEY (location) REFERENCES locations(id)
        #     )
        # """
        # )
        # # Ensure there's only one row in game_state (id=1)
        # self.cursor.execute("INSERT OR IGNORE INTO game_state (id) VALUES (1)")

        # Create the npcs table if it doesn't exist.
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS npcs (
                name TEXT PRIMARY KEY,
                description TEXT,
                location_name TEXT,
                behavior_type TEXT,
                appearance TEXT,
                bonds TEXT,
                ideals TEXT,
                flaws TEXT,
                role TEXT,
                traits TEXT,
                gender TEXT,
                affinity_score INTEGER,
                affinity_type TEXT
            )
        """
        )
        self.conn.commit()

        # Create the npcs table if it doesn't exist.
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS quests (
                name TEXT PRIMARY KEY,
                description TEXT,
                objective TEXT,
                giver TEXT
            )
        """
        )
        self.conn.commit()

    # def get_game_state(self):
    #     self.cursor.execute("SELECT date, location, mode FROM game_state WHERE id = 1")
    #     row = self.cursor.fetchone()
    #     if row:
    #         return {"date": row[0], "location": row[1], "mode": row[2]}
    #     else:
    #         return None

    # # TODO Use this instead of json file?
    # def set_game_state(self, **kwargs):
    #     # Build the query dynamically
    #     columns = ", ".join(kwargs.keys())
    #     placeholders = ", ".join("?" * len(kwargs))
    #     values = list(kwargs.values())
    #     # Ensure id=1
    #     self.cursor.execute(
    #         f"""
    #         INSERT OR REPLACE INTO game_state (id, {columns})
    #         VALUES (1, {placeholders})
    #     """,
    #         (values,),
    #     )
    #     self.conn.commit()

    # def update_game_state(self, **kwargs):
    #     # Build the query dynamically
    #     assignments = ", ".join([f"{key}=?" for key in kwargs.keys()])
    #     values = list(kwargs.values())
    #     # Ensure id=1
    #     self.cursor.execute(
    #         f"""
    #         UPDATE game_state
    #         SET {assignments}
    #         WHERE id = 1
    #     """,
    #         (values,),
    #     )
    #     self.conn.commit()

    def close(self):
        self.conn.close()

    def save_location(self, location: Location):
        npcs = json.dumps([npc.name for npc in location.npcs])
        sublocations = json.dumps(location.sublocations)

        self.cursor.execute(
            """
            INSERT OR REPLACE INTO locations (
                name, description, npcs, parent_location, sublocations,
                location_type, attributes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                location.name,
                str(location.description),
                npcs,
                location.parent_location,
                sublocations,
                str(location.location_type),
                str(location.attributes),
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
                npcs,
                parent_location,
                sublocations,
                location_type,
                attributes,
            ) = row
            location = Location(
                name=name,
                description=description,
                npcs=[self.get_npc(npc_name) for npc_name in json.loads(npcs)],
                parent_location=parent_location,
                sublocations=json.loads(sublocations),
                location_type=location_type,
                attributes=attributes,
            )
            logger.debug(f"Location '{name}' loaded from the database.")
            return location
        else:
            logger.debug(f"Location '{name}' not found in the database.")
            return None

    def get_all_locations(self) -> list[Location]:
        self.cursor.execute(
            "SELECT * FROM locations",
        )
        locations = []
        for row in self.cursor.fetchall():
            if row:
                (
                    name,
                    description,
                    npcs,
                    parent_location,
                    sublocations,
                    location_type,
                    attributes,
                ) = row
                locations.append(
                    Location(
                        name=name,
                        description=description,
                        npcs=[self.get_npc(npc_name) for npc_name in json.loads(npcs)],
                        parent_location=parent_location,
                        sublocations=json.loads(sublocations),
                        location_type=location_type,
                        attributes=attributes,
                    )
                )
                logger.debug(f"Location '{name}' loaded from the database.")
            else:
                logger.debug(f"Location '{name}' not found in the database.")
        return locations

    def save_npc(self, npc: NPC):
        """Save or update an NPC instance in the database."""
        logger.debug(f"Inserting NPC: {asdict(npc)}")
        self.cursor.execute(
            """
            INSERT OR REPLACE INTO npcs (
                name, description,
                location_name, behavior_type, appearance,
                bonds, ideals, flaws, role,
                traits, gender, affinity_score, affinity_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                npc.name,
                str(npc.description),
                str(npc.location_name),
                str(npc.behavior_type),
                str(npc.appearance),
                str(npc.bonds),
                str(npc.ideals),
                str(npc.flaws),
                str(npc.role),
                str(npc.traits),
                str(npc.gender),
                npc.affinity_score,
                npc.affinity_type,
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

    def npc_name_used(self, name: str) -> bool:
        """determine if an NPC already exists with the name given."""
        self.cursor.execute(
            "SELECT * FROM npcs WHERE name = ?",
            (name,),
        )
        row = self.cursor.fetchone()
        logger.debug(f"row: {row}, bool(row): {row}")
        return bool(row)

    def get_all_npcs(self) -> list[NPC]:
        self.cursor.execute(
            "SELECT * FROM npcs",
        )
        npcs = []
        for row in self.cursor.fetchall():
            npcs.append(NPC(*row))

        return npcs

    def save_quest(self, quest: Quest):
        self.cursor.execute(
            """
            INSERT OR REPLACE INTO quests (
                name, description, objective, giver
            ) VALUES (?, ?, ?, ?)
        """,
            (
                quest.name,
                quest.description,
                quest.objective,
                quest.giver,
            ),
        )
        self.conn.commit()
        logger.debug(f"Quest '{quest.name}' saved to the database.")

    def get_quest(self, name: str) -> Optional[Quest]:
        self.cursor.execute(
            "SELECT * FROM quests WHERE name = ?",
            (name,),
        )
        row = self.cursor.fetchone()
        if row:
            (
                name,
                description,
                objective,
                giver,
            ) = row
            quest = Quest(
                name=name,
                description=description,
                objective=objective,
                giver=giver,
            )
            logger.debug(f"Quest '{name}' loaded from the database.")
            return quest
        else:
            logger.debug(f"Quest '{name}' not found in the database.")
            return None
