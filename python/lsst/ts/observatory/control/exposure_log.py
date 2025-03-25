# This file is part of ts_observatory_control.
#
# Developed for the Vera Rubin Observatory Telescope and Site Systems.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import asyncio
import json
from typing import Any, Dict, List


class ExposureLog:
    """A class to manage and log calibration exposures with
       associated metadata.

    The `ExposureLog` class provides an asynchronous interface to
    record, update, retrieve, and serialize exposure entries. Each
    exposure entry includes a unique identifier and associated
    metadata, such as status labels and error messages.

    Attributes:
        _entries (List[Dict[str, Any]]): Internal list to store
               exposure entries.
        _lock (asyncio.Lock): An asynchronous lock to ensure
               thread-safe operations.
    """

    def __init__(self) -> None:
        self._entries: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def add_entry(self, exposure_id: str, metadata: Dict[str, Any]) -> None:
        """Add a new exposure entry to the log.

        This method records a new exposure with its unique identifier
        and associated metadata. Makes sure the operation is
        thread-safe by acquiring an asynchronous lock during the
        update.

        Args:
            exposure_id (str): A unique identifier for the exposure.
            metadata (Dict[str, Any]): A dictionary containing
                metadata about the exposure, such as status,
                timestamps, labels, and any relevant notes.

        Example:
            ```python
            await exposure_log.add_entry(
                exposure_id="exposure_001",
                metadata={
                    "status": "pending",
                    "wavelength": 500.0,
                    "error_message": None
                }
            )
            ```
        """
        async with self._lock:
            self._entries.append({"exposure_id": exposure_id, **metadata})

    async def update_entry(self, exposure_id: str, metadata: Dict[str, Any]) -> None:
        """Update an existing exposure entry with new metadata.

        This method searches for an exposure entry by its unique identifier
        and updates its metadata with the provided information. If the exposure
        ID is not found, the method does nothing.

        Args:
            exposure_id (str): The unique identifier of the exposure to update.
            metadata (Dict[str, Any]): A dictionary containing the metadata
            fields to update.

        Example:
            ```python
            await exposure_log.update_entry(
                exposure_id="exposure_001",
                metadata={
                    "status": "success",
                    "error_message": None
                }
            )
            ```
        """
        async with self._lock:
            for entry in self._entries:
                if entry["exposure_id"] == exposure_id:
                    entry.update(metadata)
                    break

    async def get_entries(self) -> List[Dict[str, Any]]:
        """Retrieve all exposure entries from the log.

        This method returns a copy of all exposure entries in the log

        Returns:
            List[Dict[str, Any]]: A list of dictionaries, each
                representing an exposure entry with its
                metadata.
        Example:
            ```python
            entries = await exposure_log.get_entries()
            for entry in entries:
                print(entry)
            ```
        """
        async with self._lock:
            return list(self._entries)

    async def serialize(self) -> str:
        """Serialize the exposure log to a JSON-formatted string.

        This method converts all exposure entries into a JSON string.

        Returns:
            str: A JSON-formatted string.

        Example:
            ```python
            json_log = await exposure_log.serialize()
            print(json_log)
            ```
        """
        entries = await self.get_entries()
        return json.dumps({"exposures": entries}, indent=2)

    async def clear(self) -> None:
        """Clear all exposure entries from the log."""
        async with self._lock:
            self._entries.clear()
