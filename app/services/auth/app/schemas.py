from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field


def _sem_byte_nulo(valor: str) -> str:
    """O bcrypt recusa byte nulo na senha, levantando exceção.

    Sem esta borda no contrato, uma senha contendo `\\x00` atravessava a
    validação e derrubava a rota com 500, onde o correto é 422. Encontrado pela
    suíte de contrato.
    """
    if "\x00" in valor:
        raise ValueError("a senha não pode conter byte nulo")
    return valor


# O bcrypt ignora tudo além de 72 bytes. Declarar o limite deixa a truncagem
# explícita no contrato, em vez de silenciosa: duas senhas longas diferentes
# não devem valer como a mesma.
Senha = Annotated[str, Field(min_length=1, max_length=72), AfterValidator(_sem_byte_nulo)]


class UserCreate(BaseModel):
    email: EmailStr
    password: Senha


class UserOut(BaseModel):
    id: int
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: EmailStr
    password: Senha
