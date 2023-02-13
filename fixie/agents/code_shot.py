from __future__ import annotations

import asyncio
import functools
import re
from typing import Callable, Dict, List, Optional, Union

import fastapi
import requests
import uvicorn
from pydantic import dataclasses as pydantic_dataclasses

from fixie import constants
from fixie.agents import utils
from fixie.agents.api import AgentQuery
from fixie.agents.api import AgentResponse
from fixie.agents.api import Message

ACCEPTED_FUNC_NAMES = re.compile(r"^\w+$")


@pydantic_dataclasses.dataclass
class AgentMetadata:
    """Metadata for a Fixie CodeShot Agent.

    This will get sent to the Fixie platform upon handshake.
    """

    base_prompt: str
    few_shots: List[str]

    def __post_init__(self):
        utils.strip_prompt_lines(self)
        utils.validate_code_shot_agent(self)


class CodeShotAgent:
    """A CodeShot agent.

    To make a CodeShot agent, simply pass a BASE_PROMPT and FEW_SHOTS:

        BASE_PROMPT = "A summary of what this agent does; how it does it; and its
        personality"

        FEW_SHOTS = '''
        Q: <Sample query that this agent supports>
        A: <Desired response for this query>

        Q: <Another sample query>
        A: <Desired response for this query>
        '''

        agent = CodeShotAgent(BASE_PROMPT, FEW_SHOTS)

    You can have FEW_SHOTS as a single string of all your few-shots separated by 2 new
    lines, or as an explicit list of one few-shot per index.

    Your few-shots may reach out to other Agents in the fixie ecosystem by
    "Ask Agent[agent_id]: <query to pass>", or reach out to some python functions
    by "Ask Func[func_name]: <query to pass>".

    There are a series of runtime `Func`s provided by the platform available for your
    agents to consume. You may also define your own python functions here to be consumed
    by your agent.

        @agent.register_func
        def func_name(query: fixie.AgentQuery) -> ReturnType:
            ...

        , where ReturnType is one of `str`, `fixie.Message`,
            or `Union[str, fixie.Message]`.

    Note that in the above, we are using the decorator `@agent.register_func` to
    register this function with the agent instance we just created.

    To check out the default `Func`s that are provided in Fixie, see:
        http://docs.fixie.ai/XXX

    """

    def __init__(self, base_prompt: str, few_shots: Union[str, List[str]]):
        if isinstance(few_shots, str):
            few_shots = _split_few_shots(few_shots)

        self.base_prompt = base_prompt
        self.few_shots = few_shots
        self._funcs: Dict[str, Callable] = {}

    def serve(self, agent_id: str, host: str = "0.0.0.0", port: int = 8181):
        """Starts serving the current agent at `{host}:{port}` via uvicorn.

        This pings Fixie upon startup to fetch the latest prompt and fewshots.

        Args:
            agent_id: Fixie agent_id that this agent will serve.
            host: The address to start listening at.
            port: The port number to start listening at.
        """
        fast_api = fastapi.FastAPI()
        fast_api.include_router(self.api_router())
        fast_api.add_event_handler("startup", lambda: asyncio.run(_ping_fixie(agent_id)))
        uvicorn.run(fast_api, host=host, port=port)

    def api_router(self) -> fastapi.APIRouter:
        """Returns a fastapi.APIRouter object that serves the agent."""
        router = fastapi.APIRouter()
        router.add_api_route("/", self._handshake, methods=["GET"])
        router.add_api_route("/{func_name}", self._serve_func, methods=["POST"])
        return router

    def register_func(
        self, func: Optional[Callable] = None, *, func_name: Optional[str] = None
    ) -> Callable:
        """A function decorator to register `Func`s with this agent.

        This decorator will not change the callable itself.

        Usage:

            agent = CodeShotAgent(base_prompt, few_shots)

            @agent.register_func
            def func(query):
                ...

        Optional Decorator Args:
            func_name: Optional function name to register this function by. If unset,
                the function name will be used.
        """
        if func is None:
            # Func is not passed in. It's the decorator being created.
            return functools.partial(self.register_func, func_name=func_name)

        if func_name is not None:
            if not ACCEPTED_FUNC_NAMES.fullmatch(func_name):
                raise ValueError(
                    f"Function names may only be alphanumerics, got {func_name!r}."
                )

        utils.validate_registered_pyfunc(func, duck_typing_okay=True)
        name = func_name or func.__name__
        if name in self._funcs:
            raise ValueError(f"Func[{name}] is already registered with agent.")
        self._funcs[name] = func
        return func

    def _handshake(self) -> AgentMetadata:
        return AgentMetadata(self.base_prompt, self.few_shots)

    def _serve_func(self, func_name: str, query: AgentQuery) -> AgentResponse:
        try:
            pyfunc = self._funcs[func_name]
        except KeyError:
            raise fastapi.HTTPException(
                status_code=404, detail=f"Func[{func_name}] doesn't exist"
            )
        output = pyfunc(query)
        try:
            return _wrap_with_agent_response(output)
        except TypeError:
            raise TypeError(
                f"Func[{func_name}] returned unexpected output of type {type(output)}."
            )


def _wrap_with_agent_response(
    value: Union[str, Message, AgentResponse]
) -> AgentResponse:
    if isinstance(value, str):
        return AgentResponse(Message(value))
    elif isinstance(value, Message):
        return AgentResponse(value)
    elif isinstance(value, AgentResponse):
        return value
    else:
        raise TypeError(f"Unexpected type to wrap: {type(value)}")


def _split_few_shots(few_shots: str) -> List[str]:
    """Split a long string of all few-shots into a list of few-shot strings."""
    # First, strip all lines to remove bad spaces.
    few_shots = "\n".join(line.strip() for line in few_shots.splitlines())
    # Then, split by "\n\nQ:".
    few_shot_splits = few_shots.split("\n\nQ:")
    few_shot_splits = [few_shot_splits[0]] + [
        "Q:" + few_shot for few_shot in few_shot_splits[1:]
    ]
    return few_shot_splits


async def _ping_fixie(agent_id: str):
    """Coroutine that pings Fixie to refresh the given agent_id."""
    return requests.post(f"{constants.FIXIE_REFRESH_URL}/{agent_id}")