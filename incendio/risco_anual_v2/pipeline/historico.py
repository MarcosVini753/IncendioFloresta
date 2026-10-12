from __future__ import annotations

from collections.abc import Mapping

import numpy as np

COLUNAS = ("anos_desde_ultima_queima", "historico_decaido", "queimou_ano_anterior")


def queimadas_da_base(est, anos: tuple[int, ...]) -> dict[int, np.ndarray]:
    return {int(a): est[f"queimou_{a}"].to_numpy(dtype=bool) for a in anos}


def atributos(queimadas: Mapping[int, np.ndarray], ano: int, teto_anos: int, tau_anos: float) -> dict[str, np.ndarray]:
    if int(teto_anos) < 1:
        raise SystemExit(f"ERRO historico: teto_anos deve ser >= 1; recebido {teto_anos}")
    if not float(tau_anos) > 0:
        raise SystemExit(f"ERRO historico: tau_anos deve ser > 0; recebido {tau_anos}")
    if not queimadas:
        raise SystemExit("ERRO historico: nenhum ano de cicatriz")
    ano = int(ano)
    n = len(next(iter(queimadas.values())))
    anteriores = sorted(int(a) for a in queimadas if int(a) < ano)
    ultimo = np.full(n, -1, dtype=np.int64)
    decaido = np.zeros(n, dtype=np.float64)
    for s in anteriores:
        q = np.asarray(queimadas[s], dtype=bool)
        ultimo[q] = s
        decaido += np.exp(-(ano - s) / float(tau_anos)) * q
    desde = np.where(ultimo >= 0, np.minimum(ano - ultimo, int(teto_anos)), int(teto_anos)).astype(np.float64)
    if ano - 1 in queimadas:
        anterior = np.asarray(queimadas[ano - 1], dtype=bool).astype(np.float64)
    else:
        anterior = np.full(n, np.nan)
    return {"anos_desde_ultima_queima": desde, "historico_decaido": decaido, "queimou_ano_anterior": anterior}


def descricao(teto_anos: int, tau_anos: float) -> dict[str, str]:
    return {
        "anos_desde_ultima_queima": f"anos_desde_ultima_queima[teto={int(teto_anos)}]",
        "historico_decaido": f"historico_decaido[tau={float(tau_anos):g}]",
        "queimou_ano_anterior": "queimou_ano_anterior",
    }
