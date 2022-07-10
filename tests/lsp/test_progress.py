############################################################################
# Copyright(c) Open Law Library. All rights reserved.                      #
# See ThirdPartyNotices.txt in the project root for additional notices.    #
#                                                                          #
# Licensed under the Apache License, Version 2.0 (the "License")           #
# you may not use this file except in compliance with the License.         #
# You may obtain a copy of the License at                                  #
#                                                                          #
#     http: // www.apache.org/licenses/LICENSE-2.0                         #
#                                                                          #
# Unless required by applicable law or agreed to in writing, software      #
# distributed under the License is distributed on an "AS IS" BASIS,        #
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. #
# See the License for the specific language governing permissions and      #
# limitations under the License.                                           #
############################################################################

import asyncio
from typing import List, Optional

import pytest

from pygls import IS_PYODIDE
from pygls.lsp.methods import CODE_LENS, PROGRESS_NOTIFICATION, WINDOW_WORK_DONE_PROGRESS_CANCEL
from pygls.lsp.types import (
    CodeLens,
    CodeLensParams,
    CodeLensOptions,
    TextDocumentIdentifier,
    WorkDoneProgressBegin,
    WorkDoneProgressEnd,
    WorkDoneProgressReport,
)
from pygls.lsp.types.basic_structures import ProgressParams
from pygls.lsp.types.window import WorkDoneProgressCancelParams
from ..conftest import ClientServer

class ConfiguredLS(ClientServer):
    def __init__(self):
        super().__init__()
        self.client.notifications: List[ProgressParams] = []

        @self.server.feature(
            CODE_LENS,
            CodeLensOptions(resolve_provider=False,
                            work_done_progress=True),
        )
        async def f1(params: CodeLensParams) -> Optional[List[CodeLens]]:
            self.server.lsp.progress.begin(
                params.work_done_token, WorkDoneProgressBegin(
                    title="starting", percentage=0)
            )
            def cancelled():
                self.server.lsp.progress.report(
                    params.work_done_token, WorkDoneProgressReport(message="cancel callback")
                )
            self.server.lsp.progress.on_cancel(params.work_done_token, cancelled)
            await asyncio.sleep(0.1)
            if self.server.lsp.progress.is_cancelled(params.work_done_token):
                self.server.lsp.progress.end(
                    params.work_done_token, WorkDoneProgressEnd(message="cancelled")
                )
            else:
                self.server.lsp.progress.report(
                    params.work_done_token,
                    WorkDoneProgressReport(message="doing", percentage=50),
                )
                self.server.lsp.progress.end(
                    params.work_done_token, WorkDoneProgressEnd(message="done")
                )
            return None

        @self.client.feature(PROGRESS_NOTIFICATION)
        def f2(params):
            self.client.notifications.append(params)
            if params.value['kind'] == 'begin' and params.token == "token_with_cancellation":
                # client cancels the progress token
                self.client.lsp.notify(
                    WINDOW_WORK_DONE_PROGRESS_CANCEL,
                    WorkDoneProgressCancelParams(token=params.token))


@ConfiguredLS.decorate()
def test_capabilities(client_server):
    _, server = client_server
    capabilities = server.server_capabilities

    provider = capabilities.code_lens_provider
    assert provider
    assert provider.work_done_progress is True


@pytest.mark.skipif(IS_PYODIDE, reason='threads are not available in pyodide.')
@ConfiguredLS.decorate()
def test_progress_notifications(client_server):
    client, _ = client_server
    client.lsp.send_request(
        CODE_LENS,
        CodeLensParams(
            text_document=TextDocumentIdentifier(uri="file://return.none"),
            work_done_token='token',
        ),
    ).result()

    assert len(client.notifications) == 3
    assert client.notifications[0].token == 'token'
    assert client.notifications[0].value == {
        "kind": "begin",
        "title": "starting",
        "percentage": 0,
    }
    assert client.notifications[1].token == 'token'
    assert client.notifications[1].value == {
        "kind": "report",
        "message": "doing",
        "percentage": 50,
    }
    assert client.notifications[2].token == 'token'
    assert client.notifications[2].value == {
        "kind": "end", "message": "done"}


@pytest.mark.skipif(IS_PYODIDE, reason='threads are not available in pyodide.')
@ConfiguredLS.decorate()
def test_progress_cancellation(client_server):
    client, _ = client_server
    client.lsp.send_request(
        CODE_LENS,
        CodeLensParams(
            text_document=TextDocumentIdentifier(uri="file://return.none"),
            work_done_token='token_with_cancellation',
        ),
    ).result()

    assert len(client.notifications) == 3
    assert client.notifications[0].token == 'token_with_cancellation'
    assert client.notifications[0].value == {
        "kind": "begin",
        "title": "starting",
        "percentage": 0,
    }
    assert client.notifications[1].token == 'token_with_cancellation'
    assert client.notifications[1].value == {
        "kind": "report",
        "message": "cancel callback",
    }
    assert client.notifications[2].token == 'token_with_cancellation'
    assert client.notifications[2].value == {
        "kind": "end", "message": "cancelled"}
