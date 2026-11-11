from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class ProviderResult:
    parsed: BaseModel
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


class AIProvider(ABC):
    name: str

    @abstractmethod
    async def generate_structured(
        self, *, prompt: str, instructions: str, response_schema: type[BaseModel]
    ) -> ProviderResult:
        raise NotImplementedError

    async def close(self) -> None:
        return None
