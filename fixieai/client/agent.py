from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from gql import gql

if TYPE_CHECKING:
    import fixieai.client as fixie_client

    FixieClient = fixie_client.FixieClient
else:
    FixieClient = Any


class Agent:
    """Provides an interface to the Fixie GraphQL Agent API.

    Args:
        client: The FixieClient instance to use.
        handle: The handle of the Agent.
    """

    def __init__(
        self,
        client: FixieClient,
        handle: str,
    ):
        self._client = client
        self._gqlclient = self._client.gqlclient
        self._handle = handle
        self._metadata: Optional[Dict[str, Any]] = None
        try:
            self._metadata = self.get_metadata()
        except ValueError:
            self._metadata = None

    @property
    def handle(self) -> Optional[str]:
        """Return the handle for this Agent."""
        return self._handle

    @property
    def agent_id(self) -> Optional[str]:
        """Return the agentId for this Agent."""
        if self._metadata is None:
            return None
        return self._metadata["agentId"]

    @property
    def name(self) -> Optional[str]:
        """Return the name for this Agent."""
        if self._metadata is None:
            return None
        return self._metadata["name"]

    @property
    def description(self) -> Optional[str]:
        """Return the description for this Agent."""
        if self._metadata is None:
            return None
        return self._metadata["description"]

    @property
    def queries(self) -> Optional[List[str]]:
        """Return the queries for this Agent."""
        if self._metadata is None:
            return None
        return self._metadata["queries"]

    @property
    def published(self) -> Optional[bool]:
        """Return the published status for this Agent."""
        if self._metadata is None:
            return None
        return self._metadata["published"]

    def get_metadata(self) -> Dict[str, Any]:
        """Return metadata about this Agent."""

        query = gql(
            """
            query getAgentByHandle($handle: String!) {
                agentByHandle(handle: $handle) {
                    agentId
                    handle
                    name
                    description
                    queries
                    published
                    owner {
                        username
                    }
                }
            }
        """
        )
        result = self._gqlclient.execute(
            query, variable_values={"handle": self._handle}
        )
        if "agentByHandle" not in result or result["agentByHandle"] is None:
            raise ValueError(f"Cannot fetch agent metadata for {self._handle}")
        return result["agentByHandle"]

    def create_agent(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        queries: Optional[List[str]] = None,
        more_info_url: Optional[str] = None,
        published: Optional[bool] = None,
    ) -> str:
        """Create a new Agent with the given parameters."""
        query = gql(
            """
            mutation CreateAgent(
                $handle: String!,
                $name: String,
                $description: String,
                $moreInfoUrl: String,
                $queries: [String!],
                $published: Boolean) {
                createAgent(
                    agentData: {
                        handle: $handle,
                        name: $name,
                        description: $description,
                        moreInfoUrl: $moreInfoUrl,
                        queries: $queries,
                        published: $published
                    }
                ) {
                    agent {
                        agentId
                    }
                }
            }
            """
        )

        # TODO(mdw): This might not be right if GraphQL requires all variables to be populated
        # in the mutation.
        variable_values: Dict[str, Any] = {"handle": self._handle}
        if name is not None:
            variable_values["name"] = name
        if description is not None:
            variable_values["description"] = description
        if more_info_url is not None:
            variable_values["moreInfoUrl"] = more_info_url
        if queries is not None:
            variable_values["queries"] = queries
        if published is not None:
            variable_values["published"] = published

        result = self._gqlclient.execute(query, variable_values=variable_values)
        if "createAgent" not in result or result["createAgent"] is None:
            raise ValueError(f"Failed to create Agent")
        assert isinstance(result["createAgent"], dict)
        assert isinstance(result["createAgent"]["agent"], dict)
        assert isinstance(result["createAgent"]["agent"]["agentId"], str)
        self._metadata = self.get_metadata()
        return result["createAgent"]["agent"]["agentId"]

    def update_agent(
        self,
        new_handle: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        queries: Optional[List[str]] = None,
        more_info_url: Optional[str] = None,
        published: Optional[bool] = None,
    ) -> str:
        """Update the Agent with the given parameters."""
        query = gql(
            """
            mutation UpdateAgent(
                $handle: String!,
                $newHandle: String,
                $name: String,
                $description: String,
                $moreInfoUrl: String,
                $queries: [String!],
                $published: Boolean) {
                updateAgent(
                    agentData: {
                        handle: $handle,
                        newHandle: $newHandle,
                        name: $name,
                        description: $description,
                        moreInfoUrl: $moreInfoUrl,
                        queries: $queries,
                        published: $published
                    }
                ) {
                    agent {
                        agentId
                    }
                }
            }
            """
        )

        variable_values: Dict[str, Any] = {"handle": self._handle}
        if new_handle is not None:
            variable_values["newHandle"] = new_handle
        if name is not None:
            variable_values["name"] = name
        if description is not None:
            variable_values["description"] = description
        if more_info_url is not None:
            variable_values["moreInfoUrl"] = more_info_url
        if queries is not None:
            variable_values["queries"] = queries
        if published is not None:
            variable_values["published"] = published

        result = self._gqlclient.execute(query, variable_values=variable_values)
        if "updateAgent" not in result or result["updateAgent"] is None:
            raise ValueError(f"Failed to update Agent")
        assert isinstance(result["updateAgent"], dict)
        assert isinstance(result["updateAgent"]["agent"], dict)
        assert isinstance(result["updateAgent"]["agent"]["agentId"], str)
        self._metadata = self.get_metadata()
        return result["updateAgent"]["agent"]["agentId"]

    def delete_agent(self) -> None:
        """Delete this Agent."""
        query = gql(
            """
            mutation DeleteAgent($handle: String!) {
                deleteAgent(handle: $handle) {
                    agent {
                        handle
                    }
                }
            }
        """
        )
        _ = self._gqlclient.execute(query, variable_values={"handle": self._handle})
