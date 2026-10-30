"""Memória de cálculo do estudo. Não treina modelos nem contrata serviços.

Uso: python3 docs/infraestrutura/calcular_cenarios.py
Biblioteca padrão; valores e premissas ficam no JSON adjacente.
"""
from __future__ import annotations

import csv
import json
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

def calculate():
    raw = json.loads((HERE / 'premissas_e_cotacoes.json').read_text())
    p = {k: D(str(v)) if isinstance(v, (int, float)) else v for k, v in raw['premissas'].items()}
    t = {k: D(str(v)) for k, v in raw['tarifas_usd'].items()}
    fx = p['dolar_planejamento'] * (1 + p['margem_cambio_encargos'])
    sources = ROOT / 'entrega_professor_v4/2_resultados/treino_MapBiomas_Fogo/tabelas'
    samples = list(csv.DictReader((sources / 'amostras_30m.csv').open()))
    m = sum(int(float(r['positivos'])) + int(float(r['negativos'])) for r in samples if r['tipo'] == 'treino')
    model_params = {r['modelo']: json.loads(r['parametros']) for r in csv.DictReader((sources / 'banco_vencedores.csv').open()) if r['cenario'] == 'AB30C'}
    manifest = json.loads((ROOT / 'incendio/produtos/risco/v4/2026/manifest.json').read_text())
    n = manifest['counts']['source_pixels']
    visits_per_pixel = sum(v['n_estimators'] * v['max_depth'] for v in model_params.values())
    work = n * 17 * visits_per_pixel
    # Cada cenário tem o MESMO escopo: dois modelos, uma atualização anual.
    archive_mo = max(D(0), p['r2_gb'] - p['r2_gb_inclusos']) * t['r2_gb_mes']
    backup_mo = p['backup_gb'] * t['backup_gb_mes']
    cloud_fixed = (archive_mo + backup_mo) * 12 * fx + p['dominio_brl_ano']
    gpu_hour = (t['gpu_6000_ada_h'] + p['disco_temporario_gb'] * t['disco_gpu_gb_mes'] / p['horas_mes_rateio_disco']) * fx
    cloud_job = p['horas_job_gpu_ano'] * gpu_hour
    c_vps = t['vps_c_mes'] * 12 * fx
    equipment = sum(D(str(r['valor'])) for r in raw['hardware'])
    cap_cpu = equipment * (1 + p['reserva_compra'])
    cap_gpu = (equipment + D(str(raw['gpu_local']['valor']))) * (1 + p['reserva_compra'])
    ac_kwh = p['climatizacao_incremental_w'] / 1000 * p['climatizacao_horas_dia'] * 365

    def own_annual(kind, arch):
        base = p['carga_base_local_c_w'] if arch == 'c' else p['carga_base_local_w']
        active = p['carga_total_gpu_w'] if kind == 'gpu' else p['carga_total_cpu_w']
        hours = p['horas_job_gpu_ano'] if kind == 'gpu' else p['horas_job_cpu_ano']
        energy = (base / 1000 * 8760 + (active - base) / 1000 * hours + ac_kwh) * p['energia_brl_kwh']
        other = p['internet_ipv4_brl_mes'] * 12 + backup_mo * 12 * fx + p['dominio_brl_ano'] + p['manutencao_fisica_brl_ano']
        return energy + other, energy

    rows = []
    for arch in ['b', 'c']:
        rows.append({'id': f'nuvem_{arch}', 'nome': f'Nuvem + opção {arch.upper()}', 'capex': D(0), 'anual': cloud_fixed + cloud_job + (c_vps if arch == 'c' else 0), 'labor': f'nuvem_{arch}'})
    for kind in ['cpu', 'gpu']:
        for arch in ['b', 'c']:
            cost, energy = own_annual(kind, arch)
            rows.append({'id': f'proprio_{kind}_{arch}', 'nome': f'Próprio {kind.upper()} + {arch.upper()}', 'capex': cap_gpu if kind == 'gpu' else cap_cpu, 'anual': cost, 'energia': energy, 'labor': f'proprio_{arch}'})
    for row in rows:
        labor = p['trabalho_humano'][row['labor']]
        initial = D(str(labor['inicial'])) * p['hora_tecnica_brl']
        annual = D(str(labor['anual'])) * p['hora_tecnica_brl']
        row['implantacao_tecnica'] = initial
        row['operacao_tecnica_ano'] = annual
        row['tco_infra'] = {str(y): row['capex'] + y * row['anual'] for y in [1, 3, 5]}
        row['tco_com_trabalho'] = {str(y): row['tco_infra'][str(y)] + initial + y * annual for y in [1, 3, 5]}

    traffic = []
    for users in raw['premissas']['visitantes_mes_cenarios']:
        gets = D(users) * p['b_gets_por_visita']
        excess = max(D(0), gets - t['r2_gets_inclusos'])
        # R2 arredonda operações excedentes para milhões inteiros.
        millions = (excess / 1000000).to_integral_value(rounding='ROUND_CEILING')
        traffic.append({'visitas': users, 'b_gb': D(users) * p['b_gb_por_visita'], 'b_gets': gets,
                        'b_excesso_brl_mes': millions * t['r2_milhao_gets'] * fx,
                        'c_gb': D(users) * p['c_gb_por_visita'],
                        'c_cpu_h_mes': D(users) * p['c_tiles_por_visita'] * (1 - p['c_cache_hit']) * p['c_segundos_cpu_tile'] / 3600})
    sensitivity = [{'horas': h, 'b': cloud_fixed + h * gpu_hour, 'c': cloud_fixed + h * gpu_hour + c_vps} for h in [12, 48, 72, 168, 720]]
    own_fixed_gpu = own_annual('gpu', 'b')[0] - ((p['carga_total_gpu_w'] - p['carga_base_local_w']) / 1000 * p['horas_job_gpu_ano'] * p['energia_brl_kwh'])
    thresholds = {}
    for speed_factor in [1, 2]:
        variable_own = (p['carga_total_gpu_w'] - p['carga_base_local_w']) / 1000 * p['energia_brl_kwh'] * speed_factor
        thresholds[str(speed_factor)] = (cap_gpu / 5 + own_fixed_gpu - cloud_fixed) / (gpu_hour - variable_own)
    return raw, {'n': n, 'm': m, 'model_params': model_params, 'node_visits': work,
                 'node_visits_per_pixel': visits_per_pixel, 'fx_efetivo': fx,
                 'archive_usd_mes': archive_mo, 'backup_usd_mes': backup_mo,
                 'cloud_fixed': cloud_fixed, 'cloud_job': cloud_job, 'cloud_gpu_hour_brl': gpu_hour,
                 'c_vps': c_vps, 'equipment_subtotal': equipment, 'cap_cpu': cap_cpu, 'cap_gpu': cap_gpu,
                 'rows': rows, 'traffic': traffic, 'sensitivity': sensitivity,
                 'break_even_cloud_hours': thresholds,
                 'gpu_24x7_brl_ano_sem_disco': t['gpu_6000_ada_h'] * 8760 * fx}


if __name__ == '__main__':
    _, result = calculate()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=lambda v: float(v) if isinstance(v, D) else v))
