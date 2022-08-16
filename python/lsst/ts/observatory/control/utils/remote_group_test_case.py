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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__all__ = ["RemoteGroupTestCase"]

import abc
import asyncio
import contextlib
import random
import time
import typing

from lsst.ts import salobj, utils

MAKE_TIMEOUT = 30  # Default time for make_script (seconds)

random.seed(47)  # for set_random_lsst_dds_domain


class RemoteGroupTestCase(metaclass=abc.ABCMeta):
    """Base class for testing groups of CSCs.

    Subclasses must:

    * Inherit both from this and `asynctest.TestCase`.
    * Override `basic_make_group` to make the script and any other
      controllers, remotes and such, and return a list of scripts,
      controllers and remotes that you made.

    A typical test will look like this:

        async def test_something(self):
            async with make_group():
                # ... test something
    """

    _index_iter = utils.index_generator()

    def run(self, result: typing.Any = None) -> None:
        """Override `run` to set a random LSST_DDS_PARTITION_PREFIX
        and set LSST_SITE=test for every test.

        https://stackoverflow.com/a/11180583
        """
        salobj.set_random_lsst_dds_partition_prefix()
        with utils.modify_environ(LSST_SITE="test"):
            super().run(result)  # type: ignore

    @abc.abstractmethod
    async def basic_make_group(self, usage: typing.Optional[int] = None) -> None:
        """Make a group as self.group.

        Make all other controllers and remotes, as well
        and return a list of the items made.

        Returns
        -------
        items : `List` [``any``]
            Controllers, Remotes and Group, or any other items
            for which to initially wait for ``item.start_task``
            and finally wait for ``item.close()``.

        Notes
        -----
        This is a coroutine in the unlikely case that you might
        want to wait for something.
        """
        raise NotImplementedError()

    async def close(self) -> None:
        """Optional cleanup before closing."""
        pass

    @contextlib.asynccontextmanager
    async def make_group(
        self,
        timeout: float = MAKE_TIMEOUT,
        usage: typing.Optional[int] = None,
        verbose: bool = False,
    ) -> typing.AsyncGenerator:
        """Create a Group.

        The group is accessed as ``self.group``.

        Parameters
        ----------
        timeout : `float`
            Timeout (sec) for waiting for ``item.start_task`` and
            ``item.close()`` for each item returned by `basic_make_script`,
            and `self.close`.
        usage: `int`
            Combined enumeration with intended usage.
        verbose : `bool`
            Log data? This can be helpful for setting ``timeout``.
        """
        items_to_await = await self.wait_for(
            self.basic_make_group(usage),
            timeout=timeout,
            description="self.basic_make_group()",
            verbose=verbose,
        )
        try:
            await self.wait_for(
                asyncio.gather(
                    *[
                        item.start_task
                        for item in items_to_await
                        if item.start_task is not None
                    ]
                ),
                timeout=timeout,
                description=f"item.start_task for {len(items_to_await)} items",
                verbose=verbose,
            )
            yield
        finally:
            await self.wait_for(
                self.close(),
                timeout=timeout,
                description="self.close()",
                verbose=verbose,
            )
            await self.wait_for(
                asyncio.gather(*[item.close() for item in items_to_await]),
                timeout=timeout,
                description=f"item.close() for {len(items_to_await)} items",
                verbose=verbose,
            )

    async def wait_for(
        self, coro: typing.Awaitable, timeout: float, description: str, verbose: bool
    ) -> typing.Any:
        """A wrapper around asyncio.wait_for that prints timing information.

        Parameters
        ----------
        coro : ``awaitable``
            Coroutine or task to await.
        timeout : `float`
            Timeout (seconds)
        description : `str`
            Description of what is being awaited.
        verbose : `bool`
            If True then print a message before waiting
            and another after that includes how long it waited.
            If False only print a message if the wait times out.
        """
        t0 = time.monotonic()
        if verbose:
            print(f"wait for {description}")
        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            dt = time.monotonic() - t0
            print(f"{description} timed out after {dt:0.1f} seconds")
            raise
        if verbose:
            dt = time.monotonic() - t0
            print(f"{description} took {dt:0.1f} seconds")
        return result
