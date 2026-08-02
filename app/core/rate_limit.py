import time
from collections import defaultdict

_MAX_TENTATIVAS = 5
_JANELA_SEGUNDOS = 900

_tentativas: dict[str, list[float]] = defaultdict(list)


def verificar_limite_login(chave: str) -> None:
    from fastapi import HTTPException

    agora = time.time()
    historico = _tentativas[chave]
    _tentativas[chave] = [t for t in historico if agora - t < _JANELA_SEGUNDOS]

    if len(_tentativas[chave]) >= _MAX_TENTATIVAS:
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas de login. Aguarde 15 minutos e tente novamente.",
        )


def registrar_falha_login(chave: str) -> None:
    _tentativas[chave].append(time.time())


def limpar_tentativas(chave: str) -> None:
    _tentativas.pop(chave, None)
