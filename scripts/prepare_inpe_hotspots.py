#!/usr/bin/env python3
"""Converte focos diários do Programa Queimadas/INPE para GeoJSON do Acre.

Fluxo esperado:
    data/raw/inpe/focos_diario_br_YYYYMMDD.csv
        -> scripts/prepare_inpe_hotspots.py
        -> frontend/public/data/inpe/focos_ac.geojson

O script usa apenas a biblioteca padrão do Python. Por padrão, ele procura o
arquivo `focos_diario_br_*.csv` mais recente disponível em `data/raw/inpe/`,
filtra os registros do Acre e gera uma FeatureCollection GeoJSON com pontos
em longitude/latitude.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = REPO_ROOT / "data" / "raw" / "inpe"
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "frontend"
    / "public"
    / "data"
    / "inpe"
    / "focos_ac.geojson"
)

INPE_OPEN_DATA_URL = (
    "https://terrabrasilis.dpi.inpe.br/queimadas/portal/dados-abertos/"
)

# O portal do INPE já usou variações de nomenclatura entre arquivos/exports.
# Mantemos aliases para que o conversor não dependa de uma única grafia.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "date_time": (
        "datahora",
        "data_hora_gmt",
        "data_hora",
        "datahora_gmt",
    ),
    "satellite": ("satelite", "satellite"),
    "country": ("pais", "country"),
    "state": ("estado", "uf", "state"),
    "municipality": ("municipio", "municipality"),
    "biome": ("bioma", "biome"),
    "days_without_rain": (
        "diasemchuva",
        "dia_sem_chuva",
        "dias_sem_chuva",
        "numero_dias_sem_chuva",
    ),
    "precipitation": ("precipitacao", "precipitation"),
    "fire_risk": ("riscofogo", "risco_fogo", "fire_risk"),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lon", "lng", "long"),
    "frp": ("frp",),
    "id": ("id_bdq", "foco_id", "id"),
}

NUMERIC_PROPERTIES = {
    "dias_sem_chuva",
    "precipitacao",
    "risco_fogo",
    "frp",
}

# Segundo a documentação do INPE, -999 representa dado inválido para alguns
# atributos meteorológicos associados aos focos.
INVALID_MINUS_999_PROPERTIES = {
    "dias_sem_chuva",
    "precipitacao",
    "risco_fogo",
}


class InputDataError(RuntimeError):
    """Erro de estrutura ou conteúdo do arquivo de entrada."""


def normalize_name(value: str) -> str:
    """Normaliza cabeçalhos/textos para comparação tolerante a variações."""
    value = value.lstrip("\ufeff").strip().lower()
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return "".join(char for char in without_accents if char.isalnum() or char == "_")


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return normalize_name(value).replace("_", "")


def resolve_path(path: Path) -> Path:
    """Interpreta caminhos relativos a partir da raiz do repositório."""
    return path if path.is_absolute() else REPO_ROOT / path


def find_latest_input() -> Path:
    candidates = sorted(DEFAULT_INPUT_DIR.glob("focos_diario_br_*.csv"))
    if not candidates:
        raise FileNotFoundError(
            "Nenhum arquivo 'focos_diario_br_*.csv' foi encontrado em "
            f"{DEFAULT_INPUT_DIR}."
        )
    return candidates[-1]


def detect_dialect(file_obj) -> csv.Dialect:
    sample = file_obj.read(8192)
    file_obj.seek(0)

    try:
        return csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        return csv.excel


def build_field_map(fieldnames: Iterable[str | None]) -> dict[str, str]:
    return {
        normalize_name(name): name
        for name in fieldnames
        if name is not None and name.strip()
    }


def resolve_field(
    field_map: dict[str, str],
    logical_name: str,
    *,
    required: bool = False,
) -> str | None:
    for alias in FIELD_ALIASES[logical_name]:
        normalized_alias = normalize_name(alias)
        if normalized_alias in field_map:
            return field_map[normalized_alias]

    if required:
        aliases = ", ".join(FIELD_ALIASES[logical_name])
        raise InputDataError(
            f"Campo obrigatório '{logical_name}' não encontrado. "
            f"Nomes aceitos: {aliases}."
        )

    return None


def parse_number(value: str | None) -> float | None:
    if value is None:
        return None

    text = value.strip()
    if not text:
        return None

    # Os CSVs oficiais normalmente usam ponto decimal. O fallback abaixo
    # também aceita arquivos que tenham sido reexportados com vírgula decimal.
    if "," in text and "." not in text:
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


def clean_property(name: str, value: str | None) -> Any:
    if value is None:
        return None

    text = value.strip()
    if not text:
        return None

    if name not in NUMERIC_PROPERTIES:
        return text

    number = parse_number(text)
    if number is None:
        return text

    if name in INVALID_MINUS_999_PROPERTIES and number == -999:
        return None

    if name == "dias_sem_chuva" and number.is_integer():
        return int(number)

    return number


def is_acre(value: str | None) -> bool:
    normalized = normalize_text(value)
    return normalized in {"ac", "acre"}


def make_feature(
    row: dict[str, str],
    fields: dict[str, str | None],
) -> dict[str, Any] | None:
    latitude = parse_number(row.get(fields["latitude"] or ""))
    longitude = parse_number(row.get(fields["longitude"] or ""))

    if latitude is None or longitude is None:
        return None

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None

    property_sources = {
        "data_hora_gmt": fields["date_time"],
        "satelite": fields["satellite"],
        "pais": fields["country"],
        "estado": fields["state"],
        "municipio": fields["municipality"],
        "bioma": fields["biome"],
        "dias_sem_chuva": fields["days_without_rain"],
        "precipitacao": fields["precipitation"],
        "risco_fogo": fields["fire_risk"],
        "frp": fields["frp"],
    }

    properties: dict[str, Any] = {
        "fonte": "Programa Queimadas/INPE",
    }

    for output_name, source_field in property_sources.items():
        if source_field is None:
            continue
        properties[output_name] = clean_property(output_name, row.get(source_field))

    feature: dict[str, Any] = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            # GeoJSON usa a ordem [longitude, latitude].
            "coordinates": [longitude, latitude],
        },
        "properties": properties,
    }

    id_field = fields["id"]
    if id_field:
        feature_id = row.get(id_field, "").strip()
        if feature_id:
            feature["id"] = feature_id

    return feature


def convert_csv(input_path: Path, output_path: Path) -> tuple[int, int, int]:
    if not input_path.exists():
        raise FileNotFoundError(f"Arquivo de entrada não encontrado: {input_path}")

    features: list[dict[str, Any]] = []
    total_rows = 0
    acre_rows = 0
    invalid_coordinates = 0

    with input_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        dialect = detect_dialect(file_obj)
        reader = csv.DictReader(file_obj, dialect=dialect)

        if not reader.fieldnames:
            raise InputDataError("O CSV não possui cabeçalho.")

        field_map = build_field_map(reader.fieldnames)
        fields: dict[str, str | None] = {
            logical_name: resolve_field(
                field_map,
                logical_name,
                required=logical_name in {"state", "latitude", "longitude"},
            )
            for logical_name in FIELD_ALIASES
        }

        state_field = fields["state"]
        assert state_field is not None

        for row in reader:
            total_rows += 1

            if not is_acre(row.get(state_field)):
                continue

            acre_rows += 1
            feature = make_feature(row, fields)

            if feature is None:
                invalid_coordinates += 1
                continue

            features.append(feature)

    collection = {
        "type": "FeatureCollection",
        "metadata": {
            "fonte": "Programa Queimadas/INPE",
            "fonte_url": INPE_OPEN_DATA_URL,
            "arquivo_origem": input_path.name,
            "estado": "Acre",
            "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
            "quantidade_focos": len(features),
        },
        "features": features,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file_obj:
        json.dump(collection, file_obj, ensure_ascii=False, indent=2)
        file_obj.write("\n")

    return total_rows, acre_rows, invalid_coordinates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Filtra focos diários do INPE para o Acre e gera GeoJSON para o frontend."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        help=(
            "CSV de entrada. Se omitido, usa o arquivo focos_diario_br_*.csv "
            "mais recente em data/raw/inpe/."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=(
            "GeoJSON de saída. Padrão: "
            "frontend/public/data/inpe/focos_ac.geojson"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        input_path = resolve_path(args.input) if args.input else find_latest_input()
        output_path = resolve_path(args.output)

        total_rows, acre_rows, invalid_coordinates = convert_csv(
            input_path,
            output_path,
        )
    except (FileNotFoundError, InputDataError, OSError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    valid_features = acre_rows - invalid_coordinates

    print(f"Entrada: {input_path.relative_to(REPO_ROOT)}")
    print(f"Linhas lidas: {total_rows}")
    print(f"Registros do Acre: {acre_rows}")
    print(f"Coordenadas inválidas descartadas: {invalid_coordinates}")
    print(f"Focos gravados no GeoJSON: {valid_features}")
    print(f"Saída: {output_path.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
