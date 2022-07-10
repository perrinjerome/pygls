import asyncio
from concurrent.futures import Future
import enum
from typing import Callable, Dict

from pygls.lsp.methods import (PROGRESS_NOTIFICATION, WINDOW_WORK_DONE_PROGRESS_CREATE)
from pygls.lsp.types.basic_structures import (ProgressParams, ProgressToken, WorkDoneProgressBegin,
                                              WorkDoneProgressEnd, WorkDoneProgressReport)
from pygls.lsp.types.window import WorkDoneProgressCancelParams, WorkDoneProgressCreateParams
from pygls.protocol import LanguageServerProtocol


class _ProgressTokenStatus(enum.Enum):
    """The status of a work done progress
    """
    Running = 0
    Cancelled = 1
    Done = 2


class Progress:
    """A class for working with client's progress bar.

    Attributes:
        _lsp(LanguageServerProtocol): Language server protocol instance
        tokens(dict): Holds progress bar tokens that are already registered
        tokens_cancel_callbacks(dict): Holds cancel callbacks if registered
    """

    def __init__(self, lsp: LanguageServerProtocol) -> None:
        self._lsp = lsp

        self.tokens: Dict[ProgressToken, _ProgressTokenStatus] = {}
        self.tokens_cancel_callbacks: Dict[ProgressToken, Callable[[], None]] = {}

    def _check_token_registered(self, token: ProgressToken) -> None:
        if token in self.tokens:
            raise Exception("Token is already registered!")

    def create(self, token: ProgressToken, callback=None) -> Future:
        """Create a server initiated work done progress.
        """
        self._check_token_registered(token)

        def on_created(*args, **kwargs):
            self.tokens[token] = _ProgressTokenStatus.Running
            if callback is not None:
                callback(*args, **kwargs)

        return self._lsp.send_request(
            WINDOW_WORK_DONE_PROGRESS_CREATE,
            WorkDoneProgressCreateParams(token=token),
            on_created,
        )

    async def create_async(self, token: ProgressToken) -> asyncio.Future:
        """Create a server initiated work done progress.
        """
        self._check_token_registered(token)

        result = await self._lsp.send_request_async(
            WINDOW_WORK_DONE_PROGRESS_CREATE,
            WorkDoneProgressCreateParams(token=token),
        )
        self.tokens[token] = _ProgressTokenStatus.Running

        return result

    def cancel_notification_received(self, params: WorkDoneProgressCancelParams) -> None:
        """Called by pgls when a cancel notification is received from client.
        """
        callback = self.tokens_cancel_callbacks.get(params.token)
        if callback:
            callback()
        self.tokens[params.token] = _ProgressTokenStatus.Cancelled

    def is_cancelled(self, token: ProgressToken) -> bool:
        """Check if work done progress was cancelled.
        """
        return self.tokens.get(token) == _ProgressTokenStatus.Cancelled

    def on_cancel(self, token: ProgressToken, cancel_callback: Callable[[], None]) -> None:
        """Register a callback to be called if the if work done progress is cancelled.
        """
        if token in self.tokens_cancel_callbacks:
            raise ValueError(f'Cancel callback for {token} already registered.')
        self.tokens_cancel_callbacks[token] = cancel_callback

    def begin(self, token: ProgressToken, value: WorkDoneProgressBegin) -> None:
        """Notify beginning of work.
        """
        return self._lsp.notify(
            PROGRESS_NOTIFICATION,
            ProgressParams(
                token=token,
                value=value
            )
        )

    def report(self, token: ProgressToken, value: WorkDoneProgressReport) -> None:
        """Notify progress of work.
        """
        self._lsp.notify(PROGRESS_NOTIFICATION, ProgressParams(token=token, value=value))

    def end(self, token: ProgressToken, value: WorkDoneProgressEnd) -> None:
        """Notify end of work.
        """
        self._lsp.notify(PROGRESS_NOTIFICATION, ProgressParams(token=token, value=value))
        self.tokens[token] = _ProgressTokenStatus.Done
        self.tokens_cancel_callbacks.pop(token, None)
