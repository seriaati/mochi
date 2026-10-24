from pydantic import BaseModel


class AccessRequestOut(BaseModel):
    """An MCP client's request for access, as the consent page shows it."""

    # As the client registered itself; anyone can claim any name.
    client_name: str | None
    # Where the code goes on approval. The host shows who really receives access.
    redirect_uri: str


class AnswerIn(BaseModel):
    approve: bool


class AnswerOut(BaseModel):
    redirect_uri: str  # back to the client, with a code or with access_denied
