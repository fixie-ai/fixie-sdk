from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import List, Union

import fastapi
import uvicorn
from pydantic import dataclasses as pydantic_dataclasses

from llamalabs.agents import utils
from llamalabs.agents.api import AgentQuery
from llamalabs.agents.api import AgentResponse
from llamalabs.agents.api import Message


@pydantic_dataclasses.dataclass
class AgentMetadata:
    """A CodeShot agent metadata that will get sent to the Llama Labs upon handshake."""

    handle: str
    base_prompt: str
    fewshots: List[str]


class CodeShotAgent(ABC):
    """Abstract CodeShot agent.

    To make a CodeShot agent, simply subclass and set the abstract fields:

        class CustomAgent(CodeShotAgent):
            handle = "llamalabs-agent-id"
            BASE_PROMPT = "A summary of what this agent does; how it does it; and its
                           personality"
            FEWSHOTS = [
                # List of fewshots go here.
            ]

    Your agent may define as many or little python functions that will be accessible by
    the fewshots. Each python function should have the following sytax:

        def func(self, query: AgentQuery) -> ReturnType:
            ...

        , where ReturnType is one of `str`, `Message` or `AgentResponse`.

    These python functions can be used in the fewshot like:
        "Ask Func[func]: The query to send to the function"
        "Func[func] says: The output of the function back"

    """

    def __init__(self):
        utils.strip_fewshot_lines(self)
        utils.validate_codeshot_agent(self)

    @property
    @abstractmethod
    def handle(self) -> str:
        raise NotImplementedError()

    @property
    @abstractmethod
    def BASE_PROMPT(self) -> str:
        raise NotImplementedError()

    @property
    @abstractmethod
    def FEWSHOTS(self) -> List[str]:
        raise NotImplementedError()

    def serve(self, host: str = "0.0.0.0", port: int = 8181):
        """Starts serving the current agent at `{host}:{port}` via uvicorn.

        Args:
            host: The address to start listening at.
            port: The port number to start listening at.
        """
        uvicorn.run(self.fast_api(), host=host, port=port)

    def fast_api(self, prefix: str = "") -> fastapi.FastAPI:
        """Returns a FastAPI object that serves the agents.

        Args:
            prefix: The sub-path to start listening at for messages from Llama Labs
                ecosystem.
        """
        router = fastapi.APIRouter(prefix=prefix)
        router.add_api_route("/", self._handshake, methods=["GET"])
        router.add_api_route("/{func_name}", self._serve_func, methods=["POST"])

        fast_api = fastapi.FastAPI()
        fast_api.include_router(router)
        return fast_api

    def _handshake(self) -> "AgentMetadata":
        return AgentMetadata(
            handle=self.handle,
            base_prompt=self.BASE_PROMPT,
            fewshots=self.FEWSHOTS,
        )

    def _serve_func(self, func_name: str, query: AgentQuery) -> AgentResponse:
        try:
            pyfunc = utils.get_pyfunc(self, func_name)
        except AttributeError:
            raise fastapi.HTTPException(
                status_code=404, detail=f"Func[{func_name}] doesn't exist"
            )
        except (ValueError, TypeError):
            raise fastapi.HTTPException(
                status_code=403, detail=f"Func[{func_name}] is not callable by api."
            )
        output = pyfunc(query)
        try:
            return _wrap_by_agent_response(output)
        except TypeError:
            raise TypeError(
                f"Func[{func_name}] returned unexpected output of type {type(output)}."
            )


def _wrap_by_agent_response(value: Union[str, Message, AgentResponse]) -> AgentResponse:
    if isinstance(value, str):
        return AgentResponse(Message(value))
    elif isinstance(value, Message):
        return AgentResponse(value)
    elif isinstance(value, AgentResponse):
        return value
    else:
        raise TypeError(f"Unexpected type to wrap: {type(value)}")