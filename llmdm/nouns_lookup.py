import logging
import os
import re
import sqlite3

from rapidfuzz import fuzz, process

from llmdm.utils import SAVE_DIR

logger = logging.getLogger(__name__)


class ProperNounDB:
    def __init__(self, save_name):
        """Initialize the database connection and create tables."""
        if not os.path.exists(SAVE_DIR):
            os.mkdir(SAVE_DIR)
        self.conn = sqlite3.connect(
            os.path.join(SAVE_DIR, f"{save_name}_proper_nouns.sql")
        )
        self.create_tables()

    def create_tables(self):
        """Create the names and nicknames tables if they don't exist."""
        cursor = self.conn.cursor()
        # Create the names table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS names (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL
            )
        """
        )
        # Create the nicknames table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS nicknames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_id INTEGER NOT NULL,
                nickname TEXT NOT NULL,
                normalized_nickname TEXT NOT NULL,
                FOREIGN KEY(name_id) REFERENCES names(id)
            )
        """
        )
        self.conn.commit()

    def normalize_name(self, name):
        """
        Normalize the name for consistent storage and lookup.
        Converts to lowercase and removes non-alphanumeric characters.
        """
        name = name.lower()
        name = re.sub(r"[^a-z0-9\s]", "", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name

    def add(self, name, nicknames=[]):
        """Add a name and their nicknames to the database."""
        logger.debug(f"name: {name}, nicknames: {nicknames}")
        if name not in nicknames:
            nicknames.append(name)

        normalized_name = self.normalize_name(name)
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO names (name, normalized_name)
            VALUES (?, ?)
        """,
            (
                name,
                normalized_name,
            ),
        )
        name_id = cursor.lastrowid
        # Insert the nicknames
        for nickname in nicknames:
            normalized_nickname = self.normalize_name(nickname)
            cursor.execute(
                """
                    INSERT INTO nicknames (name_id, nickname, normalized_nickname)
                    VALUES (?, ?, ?)
                """,
                (
                    name_id,
                    nickname,
                    normalized_nickname,
                ),
            )
        self.conn.commit()

    def get_all_names(self):
        """Retrieve all names (canonical and nicknames) with their name_id."""
        cursor = self.conn.cursor()
        # Get all canonical names
        cursor.execute(
            """
            SELECT id, normalized_name FROM names
            """
        )
        names = cursor.fetchall()
        # Get all nicknames
        cursor.execute(
            """
            SELECT name_id, normalized_nickname FROM nicknames
            """
        )
        nicknames = cursor.fetchall()
        # Combine into a list of tuples: (name_id, normalized_name)
        all_names = [(name_id, normalized_name) for name_id, normalized_name in names]
        all_names.extend(nicknames)
        return all_names

    def get_canonical_name(self, name_id):
        """Retrieve the canonical name for a given name_id."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT name FROM names WHERE id=?
        """,
            (name_id,),
        )
        result = cursor.fetchone()
        return result[0] if result else None

    def fuzzy_lookup(self, query, threshold=10, limit=10):
        """
        Perform a fuzzy lookup for a given query.

        Parameters:
        - query (str): The name to search for.
        - threshold (int): Minimum score for matches (0-100).
        - limit (int): Maximum number of results to return.
        """
        normalized_query = self.normalize_name(query)
        all_names = self.get_all_names()  # List of tuples: (name_id, normalized_name)
        names_list = [name for _, name in all_names]
        matches = process.extract(
            normalized_query,
            names_list,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=threshold,
            limit=limit,
        )
        results = []
        logger.debug(f"fuzzy_lookup: {matches=}")
        for match in matches:
            matched_name = match[0]
            score = match[1]
            # Find the name_id(s) corresponding to the matched name
            matched_name_ids = [
                name_id for name_id, name in all_names if name == matched_name
            ]
            for name_id in matched_name_ids:
                canonical_name = self.get_canonical_name(name_id)
                if canonical_name:
                    results.append({"name": canonical_name, "score": score})
        # Remove duplicates
        unique_results = []
        seen = set()
        logger.debug(f"fuzzy_lookup: {results=}")
        for result in results:
            if result["name"] not in seen:
                unique_results.append(result)
                seen.add(result["name"])
        if not unique_results:
            logger.debug(f"fuzzy_lookup:\n{normalized_query=}\n{all_names=}")

        return unique_results[0]["name"]

    def close(self):
        """Close the database connection."""
        self.conn.close()
