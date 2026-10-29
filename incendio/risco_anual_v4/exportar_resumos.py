"""Deriva resumos dos COGs v4 sem alterar mapas/modelos recebidos.

incendio/.venv/bin/python incendio/risco_anual_v4/exportar_resumos.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyproj
import rasterio
from rasterio.io import MemoryFile
from rasterio.windows import Window, from_bounds

BASE = Path(__file__).resolve().parents[1]
MODELS = ("random_forest", "xgboost")
CLASSES = ("very_low", "low", "moderate", "high", "very_high")
CUTS = [50, 70, 90, 95]
METHODS = {
    "mean": "Média dos percentis recebidos; pesos iguais por pixel válido",
    "mode": "Classe mais frequente; empate pela menor classe",
    "median": "Quantil exato 0.5; inverted_cdf, posição ceil(0.5*n)",
    "concentration": "100 * count(percentil >= 90) / n; cobertura aproximada",
    "p75": "Quantil exato 0.75; inverted_cdf, posição ceil(0.75*n)",
    "area_mean": "Média dos percentis ponderada pela área geodésica WGS84",
    "local_rarity": "Média das médias das classes ocupadas no grupo",
    "state_rarity": "Peso por pixel = 1/frequência estadual de sua classe",
    "state_cdf": "100 * count(valor_banda1 <= média_banda1_grupo) / N estadual",
}


def load(path):
    return json.loads(path.read_text())


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def exact_quantiles(values):
    """Partição apenas sobre cópia/arquivo temporário, nunca sobre um COG."""
    if not len(values):
        raise ValueError("Grupo sem pixels válidos")
    ranks = [math.ceil(q * len(values)) - 1 for q in (.5, .75)]
    values.partition(ranks)
    return [float(values[k]) for k in ranks]


def weighted_summaries(counts, sums, frequencies):
    occupied = counts > 0
    means = np.divide(sums, counts, out=np.zeros_like(sums), where=occupied)
    local = float(means.sum() / occupied.sum())
    weights = np.divide(1., frequencies, out=np.zeros(5), where=frequencies > 0)
    statewide = float(np.dot(sums, weights) / np.dot(counts, weights))
    return local, statewide


def group_key(group_id):
    match = re.fullmatch(r"AC-5KM-E(-?\d+)N(\d+)", group_id)
    if not match:
        raise ValueError("ID de grupo inválido")
    x, y = map(int, match.groups())
    return x * 10000 + y


def audit_group(root, index, group_id):
    """Outra leitura, por janelas de 5 km, para auditar quantis e bordas."""
    key = group_key(group_id)
    x, y = divmod(key, 10000)
    t = np.linspace(0, 5000, 21)
    xx = np.r_[x*5000+t, x*5000+t, np.full(21,x*5000), np.full(21,(x+1)*5000)]
    yy = np.r_[np.full(21,y*5000), np.full(21,(y+1)*5000), y*5000+t, y*5000+t]
    inverse = pyproj.Transformer.from_crs(31979, 4326, always_xy=True)
    project = pyproj.Transformer.from_crs(4326, 31979, always_xy=True)
    lon, lat = inverse.transform(xx, yy)
    bounds = (lon.min()-.0003, lat.min()-.0003, lon.max()+.0003, lat.max()+.0003)
    parts = []
    for entry in index["sectors"]:
        w,s,e,n = entry["bbox"]
        if e < bounds[0] or w > bounds[2] or n < bounds[1] or s > bounds[3]:
            continue
        with rasterio.open(root/entry["url"]) as ds:
            win = from_bounds(*bounds, ds.transform)
            x0,y0 = max(0,math.floor(win.col_off)),max(0,math.floor(win.row_off))
            x1,y1 = min(ds.width,math.ceil(win.col_off+win.width)),min(ds.height,math.ceil(win.row_off+win.height))
            if x1<=x0 or y1<=y0:
                continue
            raw = ds.read(window=Window(x0,y0,x1-x0,y1-y0))
            rows,cols = np.nonzero(raw[0] != ds.nodata)
            lng = ds.transform.c+(cols+x0+.5)*ds.transform.a
            ltt = ds.transform.f+(rows+y0+.5)*ds.transform.e
            gx,gy = project.transform(lng,ltt)
            keys = np.floor(gx/5000).astype(np.int64)*10000+np.floor(gy/5000).astype(np.int64)
            parts.append(raw[:,rows,cols][:,keys==key])
    return np.concatenate(parts,axis=1)


def build(year):
    root = BASE/f"produtos/risco/v4/{year}"
    manifest,index,grid = [load(root/name) for name in ("manifest.json","index.json","grid.geojson")]
    props = [f["properties"] for f in grid["features"]]
    ids = [p["id"] for p in props]
    keys = np.array([group_key(i) for i in ids])
    counts = np.array([p["n_source_pixels"] for p in props],dtype=np.int64)
    total,g = int(counts.sum()),len(ids)
    if year!=manifest["year"] or year!=index["year"] or total!=index["valid_pixels"] or not np.all(np.diff(keys)>0):
        raise ValueError("Cobertura ou ano incompatível")
    offsets = np.r_[0,counts.cumsum()]
    written = np.zeros(g,dtype=np.int64)
    hits = np.zeros(g,dtype=np.int64)
    sums = np.zeros((g,4))
    per_class = np.zeros((g,2,5),dtype=np.int64)
    class_sums = np.zeros((g,2,5))
    areas = np.zeros(g)
    area_sums = np.zeros((g,2))
    thresholds = [np.unique([p[f"value_{m}"] for p in props]) for m in MODELS]
    cdf_counts = [np.zeros(len(t)+1,dtype=np.int64) for t in thresholds]
    input_hashes = {name:digest(root/name) for name in ("manifest.json","index.json","grid.geojson")}
    sector_hashes = {}
    geod = pyproj.Geod(ellps="WGS84")
    a,b,c,d,e,f = index["transform"]
    if b or d:
        raise ValueError("Grade rotacionada")
    row_areas = np.array([abs(geod.polygon_area_perimeter([c,c+a,c+a,c],[f+r*e,f+r*e,f+(r+1)*e,f+(r+1)*e])[0]) for r in range(index["height"])])
    project = pyproj.Transformer.from_crs(4326,31979,always_xy=True)
    # ~1.3 GiB em disco por ano; uma janela e um grupo em RAM.
    cache = BASE/"resultados/aggregation_stats"
    cache.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{year}-",dir=cache) as scratch, rasterio.Env(GDAL_CACHEMAX=64*1024*1024):
        pixels = np.memmap(Path(scratch)/"percentiles.dat",dtype="float32",mode="w+",shape=(2,total))
        for i,entry in enumerate(index["sectors"],1):
            payload = (root/entry["url"]).read_bytes()
            if len(payload)!=entry["bytes"]:
                raise ValueError("Setor truncado")
            sector_hashes[entry["id"]] = hashlib.sha256(payload).hexdigest()
            with MemoryFile(payload) as mem,mem.open() as ds:
                raw = ds.read()
                mask = raw[0]!=ds.nodata
                if not np.all((raw!=ds.nodata)==mask[None]) or int(mask.sum())!=entry["valid_pixels"]:
                    raise ValueError("Máscara incompatível")
                values = raw[:,mask]
                if not np.isfinite(values).all() or np.any((values<0)|(values>100)):
                    raise ValueError("Domínio inválido")
                rr,cc = np.nonzero(mask)
                lon = ds.transform.c+(cc+.5)*ds.transform.a
                lat = ds.transform.f+(rr+.5)*ds.transform.e
            x,y = project.transform(lon,lat)
            native_keys = np.floor(x/5000).astype(np.int64)*10000+np.floor(y/5000).astype(np.int64)
            local,inv,nlocal = np.unique(native_keys,return_inverse=True,return_counts=True)
            positions = np.searchsorted(keys,local)
            if np.any(positions>=g) or not np.array_equal(keys[positions],local):
                raise ValueError("Pixel sem grupo")
            pixel_areas = row_areas[rr+entry["window"][1]]
            areas[positions] += np.bincount(inv,weights=pixel_areas,minlength=len(local))
            for band in range(4):
                sums[positions,band] += np.bincount(inv,weights=values[band],minlength=len(local))
            for mi in range(2):
                pct = values[mi*2+1]
                category = np.searchsorted(CUTS,pct,side="right")
                per_class[positions,mi] += np.bincount(inv*5+category,minlength=len(local)*5).reshape(-1,5)
                class_sums[positions,mi] += np.bincount(inv*5+category,weights=pct,minlength=len(local)*5).reshape(-1,5)
                area_sums[positions,mi] += np.bincount(inv,weights=pct.astype(np.float64)*pixel_areas,minlength=len(local))
                cdf_counts[mi] += np.bincount(np.searchsorted(thresholds[mi],values[mi*2].astype(np.float64),side="left"),minlength=len(thresholds[mi])+1)
            order = np.argsort(inv,kind="stable")
            start = 0
            for position,length in zip(positions,nlocal):
                offset = offsets[position]+written[position]
                if written[position]+length>counts[position]:
                    raise ValueError("Grupo com pixels excedentes")
                indices = order[start:start+length]
                pixels[0,offset:offset+length] = values[1,indices]
                pixels[1,offset:offset+length] = values[3,indices]
                written[position] += length
                hits[position] += 1
                start += length
            if i%26==0 or i==len(index["sectors"]):
                print(f"{year}: {i}/{len(index['sectors'])} setores; pixels preservados em disco",flush=True)
        if not np.array_equal(written,counts):
            raise ValueError("Contagem divergente")
        state_counts = per_class.sum(axis=0)
        frequencies = state_counts/total
        cdfs = [v.cumsum()[:-1] for v in cdf_counts]
        groups = {}
        for gi,p in enumerate(props):
            models = {}
            for mi,m in enumerate(MODELS):
                n = int(counts[gi]);cs = per_class[gi,mi]
                expected = np.rint([p[f"share_{m}_{cl}"]*n for cl in CLASSES]).astype(np.int64)
                if not np.array_equal(cs,expected) or not np.allclose(sums[gi,mi*2:mi*2+2]/n,[p[f"value_{m}"],p[f"percentile_{m}"]],atol=1e-9,rtol=0):
                    raise ValueError("Resultados divergentes do produto científico")
                median,p75 = exact_quantiles(pixels[mi,offsets[gi]:offsets[gi+1]])
                local,wide = weighted_summaries(cs,class_sums[gi,mi],frequencies[mi])
                le = int(cdfs[mi][np.searchsorted(thresholds[mi],p[f"value_{m}"])])
                models[m] = dict(median=median,p75=p75,area_mean=float(area_sums[gi,mi]/areas[gi]),
                    class_counts=cs.tolist(),class_means=[float(s/nn) if nn else None for s,nn in zip(class_sums[gi,mi],cs)],
                    local_rarity=local,state_rarity=wide,state_cdf=100*le/total,state_cdf_count_le=le)
            groups[p["id"]] = dict(n_source_pixels=int(counts[gi]),valid_area_m2=float(areas[gi]),models=models)
        samples = {0,g//2,g-1,ids.index("AC-5KM-E105N1773")}
        cross = np.flatnonzero((hits>1)&(counts>=28000))
        if len(cross): samples.add(int(cross[0]))
        for gi in sorted(samples):
            original = audit_group(root,index,ids[gi])
            if original.shape[1]!=counts[gi]: raise ValueError("Auditoria independente: contagem")
            for mi,m in enumerate(MODELS):
                expected = np.quantile(original[mi*2+1],[.5,.75],method="inverted_cdf")
                actual = groups[ids[gi]]["models"][m]
                if not np.array_equal(expected,[actual["median"],actual["p75"]]):
                    raise ValueError("Auditoria independente: quantis")
        del pixels
    result = dict(schema_version="1.0",product="risk_v4_aggregation_stats",year=year,
        generated_at=datetime.now(timezone.utc).isoformat(),source_identity=manifest["provenance"]["identity"],
        input_sha256=input_hashes,sector_sha256=sector_hashes,exporter_sha256=digest(Path(__file__)),
        counts=dict(groups=g,source_pixels=total),methods=METHODS,
        quantile_method="inverted_cdf",area_method="WGS84_geodesic_pixel_corners",cdf_method="empirical_less_or_equal",
        state_class_counts={m:state_counts[mi].tolist() for mi,m in enumerate(MODELS)},
        state_frequencies={m:frequencies[mi].tolist() for mi,m in enumerate(MODELS)},
        audit_groups=[ids[i] for i in sorted(samples)],groups=groups)
    target = root/"aggregation-stats.json"
    staging = target.with_suffix(".json.tmp")
    staging.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"),allow_nan=False)+"\n")
    staging.replace(target)
    print(f"{year}: publicado {target}; {g} grupos, {total:,} pixels; auditoria independente aprovada",flush=True)
    return result


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year",type=int,choices=(2025,2026))
    args = parser.parse_args()
    for year in ((args.year,) if args.year else (2025,2026)):
        build(year)
