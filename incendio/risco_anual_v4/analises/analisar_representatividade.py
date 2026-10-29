"""Estudo descritivo dos pixels publicados; não modifica produtos nem o site.

Uso, na raiz: incendio/.venv/bin/python \
  incendio/risco_anual_v4/analises/analisar_representatividade.py

Requer NumPy, Rasterio, PyProj e Matplotlib. Lê os pixels originais dos COGs,
exclui NoData e audita as médias/proporções contra os GeoJSONs publicados.
Quantis por grupo são intervalos de histograma de largura 0,5 no índice;
o exemplo citado pelo usuário é calculado exatamente dos pixels originais.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyproj
import rasterio

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent / "representatividade"
MODELS = ("random_forest", "xgboost")
CLASS_IDS = ("very_low", "low", "moderate", "high", "very_high")
CLASS_LABELS = ("Muito baixo", "Baixo", "Moderado", "Alto", "Muito alto")
COLORS = ("#238677", "#8cc89a", "#efd47b", "#e9a066", "#cb5c52")
CUTS = np.array([50, 70, 90, 95])
EXAMPLE = "AC-5KM-E105N1773"
BINS = 201  # [0,0.5), ..., [99.5,100), {100}
VALUE_EDGES = np.r_[0.0, np.geomspace(1e-9, 100, 2001)]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(name, value):
    (OUTPUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                         allow_nan=False) + "\n")


def quantile_intervals(histogram, q, step=0.5):
    rank = np.ceil(histogram.sum(axis=-1) * q).astype(np.int64)
    b = (histogram.cumsum(axis=-1) < rank[..., None]).sum(axis=-1)
    return b * step, np.minimum((b + 1) * step, 100)


def analyze_year(year):
    root = ROOT / f"produtos/risco/v4/{year}"
    grid = read(root / "grid.geojson")
    index = read(root / "index.json")
    manifest = read(root / "manifest.json")
    props = [f["properties"] for f in grid["features"]]
    n = np.array([p["n_source_pixels"] for p in props], dtype=np.int64)
    group_ids = [p["id"] for p in props]
    parsed = [re.fullmatch(r"AC-5KM-E(-?\d+)N(\d+)", k).groups() for k in group_ids]
    keys = np.array([int(x) * 10000 + int(y) for x, y in parsed])
    assert np.all(np.diff(keys) > 0) and n.sum() == index["valid_pixels"]
    g = len(props)
    hist = np.zeros((g, 2, BINS), dtype=np.int64)
    class_sums = np.zeros((g, 2, 5))
    sums = np.zeros((g, 4))
    areas = np.zeros(g)
    area_sums = np.zeros((g, 2))
    value_hist = np.zeros((2, len(VALUE_EDGES) - 1), dtype=np.int64)
    moments = np.zeros((4, 2))
    limits = np.array([[np.inf, -np.inf]] * 4)
    integer_counts = np.zeros(4, dtype=np.int64)
    # Exact empirical CDF evaluated at each published mean model value.
    cdf_thresholds = [np.unique([p[f"value_{m}"] for p in props]) for m in MODELS]
    cdf_counts = [np.zeros(len(t) + 1, dtype=np.int64) for t in cdf_thresholds]
    example_parts = []
    example_areas = []
    ex = group_ids.index(EXAMPLE)
    project = pyproj.Transformer.from_crs(4326, 31979, always_xy=True)
    a, b, c, d, e, f = index["transform"]
    assert b == 0 and d == 0
    geod = pyproj.Geod(ellps="WGS84")
    row_areas = np.array([
        abs(geod.polygon_area_perimeter(
            [c, c+a, c+a, c],
            [f+r*e, f+r*e, f+(r+1)*e, f+(r+1)*e],
        )[0]) for r in range(index["height"])
    ])
    for k, sector in enumerate(index["sectors"], 1):
        with rasterio.open(root / sector["url"]) as ds:
            raw = ds.read()  # no out_shape: never reads an overview
            valid = raw[0] != ds.nodata
            assert np.all((raw != ds.nodata) == valid[None])
            values = raw[:, valid]
            assert np.isfinite(values).all() and np.all((values >= 0) & (values <= 100))
            assert values.shape[1] == sector["valid_pixels"]
            rows, cols = np.nonzero(valid)
            lon = ds.transform.c + (cols + 0.5) * ds.transform.a
            lat = ds.transform.f + (rows + 0.5) * ds.transform.e
        x, y = project.transform(lon, lat)
        native_keys = np.floor(x/5000).astype(np.int64)*10000 + np.floor(y/5000).astype(np.int64)
        local_keys, inverse = np.unique(native_keys, return_inverse=True)
        positions = np.searchsorted(keys, local_keys)
        assert np.array_equal(keys[positions], local_keys)
        size = len(local_keys)
        pixel_areas = row_areas[rows + sector["window"][1]]
        areas[positions] += np.bincount(inverse, weights=pixel_areas, minlength=size)
        for band in range(4):
            v = values[band].astype(np.float64)
            sums[positions, band] += np.bincount(inverse, weights=v, minlength=size)
            moments[band] += [v.sum(), np.dot(v, v)]
            limits[band, 0] = min(limits[band, 0], float(v.min()))
            limits[band, 1] = max(limits[band, 1], float(v.max()))
            integer_counts[band] += np.count_nonzero(v == np.floor(v))
        for model in range(2):
            pct = values[model*2+1].astype(np.float64)
            bucket = np.floor(pct*2).astype(np.int64)
            hist[positions, model] += np.bincount(
                inverse*BINS + bucket, minlength=size*BINS,
            ).reshape(size, BINS)
            category = np.searchsorted(CUTS, pct, side="right")
            class_sums[positions, model] += np.bincount(
                inverse*5+category, weights=pct, minlength=size*5,
            ).reshape(size, 5)
            area_sums[positions, model] += np.bincount(
                inverse, weights=pct*pixel_areas, minlength=size,
            )
            value = values[model*2].astype(np.float64)
            value_hist[model] += np.histogram(value, bins=VALUE_EDGES)[0]
            # Cumulative sum at threshold j counts all native values <= t[j].
            cdf_counts[model] += np.bincount(
                np.searchsorted(cdf_thresholds[model], value, side="left"),
                minlength=len(cdf_thresholds[model])+1,
            )
        if keys[ex] in local_keys:
            mask = native_keys == keys[ex]
            example_parts.append(values[:, mask].copy())
            example_areas.append(pixel_areas[mask])
        if k % 26 == 0 or k == len(index["sectors"]):
            print(f"{year}: {k}/{len(index['sectors'])} setores lidos na resolução original", flush=True)
    assert np.all(hist.sum(axis=-1) == n[:, None])
    example = np.concatenate(example_parts, axis=1).astype(np.float64)
    example_area = np.concatenate(example_areas)
    assert example.shape[1] == n[ex]
    results = dict(year=year, groups=g, valid_pixels=int(n.sum()),
                   provenance_identity=manifest["provenance"]["identity"],
                   input_sha256={name: sha(root/name) for name in ("grid.geojson", "index.json", "manifest.json")},
                   quantile_method="inverse_empirical_cdf; group values enclosed in 0.5-wide intervals; example exact",
                   models={})
    rows_out = []
    map_data = {}
    for mi, model in enumerate(MODELS):
        mean = np.array([p[f"percentile_{model}"] for p in props])
        published_values = np.array([p[f"value_{model}"] for p in props])
        counts = np.stack([hist[:, mi, lo:hi].sum(axis=1) for lo,hi in ((0,100),(100,140),(140,180),(180,190),(190,201))], axis=1)
        expected = np.rint(np.array([[p[f"share_{model}_{cl}"] for cl in CLASS_IDS] for p in props])*n[:,None]).astype(np.int64)
        assert np.array_equal(counts, expected)
        assert np.allclose(sums[:,mi*2]/n, published_values, rtol=0, atol=1e-9)
        assert np.allclose(sums[:,mi*2+1]/n, mean, rtol=0, atol=1e-9)
        current = np.searchsorted(CUTS, mean, side="right")
        modal = counts.argmax(axis=1)  # ties: lowest class, documented below
        shares = counts/n[:,None]
        median_lo,median_hi = quantile_intervals(hist[:,mi], .5)
        p75_lo,p75_hi = quantile_intervals(hist[:,mi], .75)
        median_cls = np.searchsorted(CUTS, median_lo, side="right")
        p75_cls = np.searchsorted(CUTS, p75_lo, side="right")
        area_mean = area_sums[:,mi]/areas
        statewide = counts.sum(axis=0)
        state_freq = statewide/n.sum()
        weights = 1/state_freq
        global_inverse = (class_sums[:,mi]*weights).sum(axis=1)/(counts*weights).sum(axis=1)
        local_inverse = np.divide(class_sums[:,mi], counts, out=np.zeros((g,5)), where=counts>0).sum(axis=1)/(counts>0).sum(axis=1)
        cdf = cdf_counts[mi].cumsum()[:-1]/n.sum()*100
        cdf_of_value_mean = cdf[np.searchsorted(cdf_thresholds[mi],published_values)]
        alternatives = {"current_mean":current,"modal_class":modal,"median_class":median_cls,
                        "p75_class":p75_cls,"inverse_local_frequency":np.searchsorted(CUTS,local_inverse,side="right"),
                        "inverse_statewide_frequency":np.searchsorted(CUTS,global_inverse,side="right"),
                        "statewide_cdf_of_mean_value":np.searchsorted(CUTS,cdf_of_value_mean,side="right"),
                        "area_weighted_mean":np.searchsorted(CUTS,area_mean,side="right")}
        comparisons={}
        for name,classes in alternatives.items():
            confusion = np.stack([counts[classes == ci].sum(axis=0) for ci in range(5)])
            comparisons[name]=dict(groups_by_class=np.bincount(classes,minlength=5).tolist(),
                native_pixel_coverage_by_display_class=(np.bincount(classes,weights=n,minlength=5)/n.sum()*100).tolist(),
                changed_groups=int((classes!=current).sum()),higher=int((classes>current).sum()),lower=int((classes<current).sum()),
                native_class_agreement_percent=float(np.trace(confusion)/n.sum()*100),
                ordinal_class_absolute_error=float((counts*np.abs(np.arange(5)[None]-classes[:,None])).sum()/n.sum()),
                very_high_pixels_displayed_as_moderate_percent=float(confusion[2,4]/statewide[4]*100),
                display_by_native_class_counts=confusion.tolist())
        ex_pct=example[mi*2+1];ex_val=example[mi*2]
        ex_classes=np.searchsorted(CUTS,ex_pct,side="right")
        ex_means=[float(ex_pct[ex_classes==cl].mean()) if np.any(ex_classes==cl) else None for cl in range(5)]
        value_q={}
        for q in (.05,.25,.5,.75,.9,.95,.99):
            i=int(np.searchsorted(value_hist[mi].cumsum(),math.ceil(n.sum()*q)))
            value_q[str(q)]=[float(VALUE_EDGES[i]),float(VALUE_EDGES[i+1])]
        full=n>=28000
        high_counts=counts[full,3:].sum(axis=1)
        for row_index,p in enumerate(props):
            row=dict(year=year,model=model,id=p["id"],longitude=p["centroid"][0],latitude=p["centroid"][1],
                n_source_pixels=int(n[row_index]),mean_percentile=float(mean[row_index]),
                mean_value_percent=float(published_values[row_index]),area_weighted_mean_percentile=float(area_mean[row_index]),
                median_lower=float(median_lo[row_index]),median_upper=float(median_hi[row_index]),
                p75_lower=float(p75_lo[row_index]),p75_upper=float(p75_hi[row_index]),
                dominant_share=float(shares[row_index].max()),share_high_or_very_high=float(shares[row_index,3:].sum()),
                inverse_local_frequency_mean=float(local_inverse[row_index]),inverse_statewide_frequency_mean=float(global_inverse[row_index]),
                statewide_cdf_of_mean_value=float(cdf_of_value_mean[row_index]))
            row.update({"class_"+name:CLASS_LABELS[int(cl[row_index])] for name,cl in alternatives.items()})
            row.update({"count_"+cl:int(counts[row_index,ci]) for ci,cl in enumerate(CLASS_IDS)})
            rows_out.append(row)
        bm=mi*2
        results["models"][model]=dict(
            native_class_counts=statewide.tolist(),native_class_shares_percent=(state_freq*100).tolist(),
            native_value=dict(mean=float(moments[bm,0]/n.sum()),std=float(np.sqrt(moments[bm,1]/n.sum()-(moments[bm,0]/n.sum())**2)),
                minimum=float(limits[bm,0]),maximum=float(limits[bm,1]),noninteger_fraction=float(1-integer_counts[bm]/n.sum()),quantile_intervals=value_q),
            native_percentile=dict(mean=float(moments[bm+1,0]/n.sum()),std=float(np.sqrt(moments[bm+1,1]/n.sum()-(moments[bm+1,0]/n.sum())**2)),
                noninteger_fraction=float(1-integer_counts[bm+1]/n.sum())),
            comparisons=comparisons,
            diagnostics=dict(modal_ties=int(((counts==counts.max(axis=1,keepdims=True)).sum(axis=1)>1).sum()),
                no_class_majority=int((shares.max(axis=1)<=.5).sum()),
                high_majority_colored_below_high=int(((counts[:,3:].sum(axis=1)>n*.5)&(current<3)).sum()),
                very_high_majority_colored_below_very_high=int(((counts[:,4]>n*.5)&(current<4)).sum()),
                max_area_weighting_difference=float(np.max(np.abs(area_mean-mean))),
                count_poisson_diagnostic=dict(subset="n_source_pixels >= 28000; exploratory heterogeneity, not a formal Poisson test",groups=int(full.sum()),
                    mean=float(high_counts.mean()),variance=float(high_counts.var()),variance_over_mean=float(high_counts.var()/high_counts.mean()))),
            example=dict(id=EXAMPLE,centroid=props[ex]["centroid"],pixels=int(n[ex]),counts=counts[ex].tolist(),
                shares_percent=(shares[ex]*100).tolist(),mean_percentile=float(mean[ex]),mean_value_percent=float(published_values[ex]),
                median=float(np.quantile(ex_pct,.5,method="inverted_cdf")),p75=float(np.quantile(ex_pct,.75,method="inverted_cdf")),
                p90=float(np.quantile(ex_pct,.9,method="inverted_cdf")),class_mean_percentiles=ex_means,
                modal_class=CLASS_LABELS[modal[ex]],share_high_or_very_high=float(shares[ex,3:].sum()*100),
                area_weighted_mean=float(area_mean[ex]),inverse_local_frequency_mean=float(local_inverse[ex]),
                inverse_statewide_frequency_mean=float(global_inverse[ex]),statewide_cdf_of_mean_value=float(cdf_of_value_mean[ex])),
        )
        map_data[model]=dict(mean=current,modal=modal,median=median_cls,p75=p75_cls,share_high=shares[:,3:].sum(axis=1))
    dump(f"resumo_{year}.json",results)
    with (OUTPUT/f"grupos_{year}.csv").open("w",newline="") as out:
        writer=csv.DictWriter(out,fieldnames=list(rows_out[0]));writer.writeheader();writer.writerows(rows_out)
    return results,grid,map_data,example,value_hist,hist.sum(axis=0)


def plot(results):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from matplotlib.colors import BoundaryNorm,ListedColormap
    from matplotlib.patches import Patch
    plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False})
    fig,axes=plt.subplots(2,2,figsize=(13,8),layout="constrained")
    for yi,result in enumerate(results):
        summary,_,_,_,_,_=result
        for mi,model in enumerate(MODELS):
            ax=axes[yi,mi];r=summary["models"][model];x=np.arange(5)
            ax.bar(x-.18,r["native_class_shares_percent"],.36,color=COLORS,label="Pixels originais",edgecolor="black",linewidth=.4)
            ax.bar(x+.18,r["comparisons"]["current_mean"]["native_pixel_coverage_by_display_class"],.36,color=COLORS,alpha=.4,hatch="//",label="Pixels em grupos com esta cor")
            ax.set_xticks(x,CLASS_LABELS,rotation=12);ax.set_ylabel("Fração dos pixels válidos (%)");ax.set_ylim(0,65)
            ax.set_title(f"{summary['year']} · {'Random Forest' if mi==0 else 'XGBoost'}");ax.legend(fontsize=8)
    fig.suptitle("Distribuição nativa e cores do mapa agregado atual\nAs colunas hachuradas atribuem a cor do grupo a todos os seus pixels.")
    fig.savefig(OUTPUT/"distribuicao_pixels_e_grupos.png",dpi=160);plt.close(fig)
    summary,grid,maps,example,_,_=results[-1]
    fig,axes=plt.subplots(2,2,figsize=(13,7.5),layout="constrained")
    polygons=[];owners=[]
    for i,feature in enumerate(grid["features"]):
        geo=feature["geometry"]
        for coords in ([geo["coordinates"]] if geo["type"]=="Polygon" else geo["coordinates"]):
            polygons.append(np.asarray(coords[0]));owners.append(i)
    owners=np.array(owners);m=maps["random_forest"]
    cmap=ListedColormap(COLORS);norm=BoundaryNorm(np.arange(-.5,5.5),cmap.N)
    for ax,key,title in zip(axes.flat,("mean","modal","median","share_high"),
        ("Atual: classe da média dos percentis","Classe predominante (moda)","Classe do pixel mediano","Fração de pixels Alto + Muito alto")):
        collection=PolyCollection(polygons,linewidths=0,rasterized=True)
        values=m[key][owners]
        if key=="share_high":collection.set_cmap("YlOrRd");collection.set_clim(0,100);collection.set_array(values*100)
        else:collection.set_cmap(cmap);collection.set_norm(norm);collection.set_array(values)
        ax.add_collection(collection);ax.autoscale_view();ax.set_aspect(1/np.cos(np.deg2rad(-9)))
        ax.set_title(title);ax.set_xlabel("Longitude");ax.set_ylabel("Latitude")
        coord=summary["models"]["random_forest"]["example"]["centroid"]
        ax.scatter(*coord,s=35,facecolors="none",edgecolors="black",linewidths=1)
        if key=="share_high":fig.colorbar(collection,ax=ax,label="% dos pixels do grupo",shrink=.7)
    fig.suptitle("Random Forest · 2026 · alternativas de resumo espacial\nCírculo: grupo citado pelo usuário. Classes representam ranking, não chance de incêndio.")
    fig.legend(handles=[Patch(color=color,label=label) for color,label in zip(COLORS,CLASS_LABELS)],
               loc="outside lower center",ncol=5,title="Classes dos três mapas categóricos")
    fig.savefig(OUTPUT/"comparacao_mapas_2026_random_forest.png",dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,4.5),layout="constrained")
    ex=summary["models"]["random_forest"]["example"]
    axes[0].bar(CLASS_LABELS,ex["shares_percent"],color=COLORS)
    axes[0].set_ylabel("Pixels do grupo (%)");axes[0].tick_params(axis="x",rotation=15)
    for i,v in enumerate(ex["shares_percent"]):axes[0].text(i,v+.7,f"{v:.1f}%",ha="center")
    axes[0].set_ylim(0,56);axes[0].set_title("Muito alto é a classe mais frequente: 48,3%")
    pct=example[1]
    axes[1].hist(pct,bins=np.linspace(0,100,101),color="#8b9f9b",weights=np.full(len(pct),100/len(pct)))
    for val,label,color in ((ex['mean_percentile'],"Média",COLORS[2]),(ex['median'],"Mediana",COLORS[3]),(ex['p75'],"P75",COLORS[4])):
        axes[1].axvline(val,color=color,lw=2,label=f"{label}: {val:.2f}")
    axes[1].set_xlabel("Percentil estadual recebido");axes[1].set_ylabel("Pixels por intervalo (%)");axes[1].legend()
    fig.suptitle(f"Grupo {EXAMPLE} · Random Forest · 2026\n28.560 pixels; média 87,24; 58,68% em Alto ou Muito alto")
    fig.savefig(OUTPUT/"exemplo_distribuicao.png",dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4),layout="constrained")
    for result in results:
        s,_,_,_,vh,ph=result
        for mi,model in enumerate(MODELS):
            label=f"{s['year']} · {'RF' if mi==0 else 'XGB'}"
            axes[0].plot(VALUE_EDGES[1:],vh[mi].cumsum()/vh[mi].sum()*100,label=label)
            axes[1].plot(np.arange(BINS)/2,ph[mi].cumsum()/ph[mi].sum()*100,label=label)
    axes[0].set_xscale("symlog",linthresh=1e-5);axes[0].set_xlabel("Valor do modelo recebido (%)");axes[0].set_ylabel("Pixels acumulados (%)");axes[0].legend(fontsize=8)
    axes[1].set_xlabel("Índice percentil recebido");axes[1].set_ylabel("Pixels acumulados (%)");axes[1].legend(fontsize=8)
    fig.suptitle("Distribuições empíricas estaduais · todos os pixels válidos\nCurva do valor usa histograma logarítmico; curva do percentil usa intervalos de 0,5.")
    fig.savefig(OUTPUT/"distribuicoes_estaduais.png",dpi=160);plt.close(fig)


if __name__=="__main__":
    OUTPUT.mkdir(parents=True,exist_ok=True)
    results=[analyze_year(y) for y in (2025,2026)]
    plot(results)
    dump("metodo.json",dict(generated_at=datetime.now(timezone.utc).isoformat(),
        source="COGs publicados, resolução original, sem treinamento ou alteração dos produtos",
        classes=CLASS_LABELS,cuts=CUTS.tolist(),quantile_histogram_width=.5,
        median_definition="inverted_cdf (nearest rank); whole-group numerical intervals, exact example",
        mode_ties="lowest class wins; number of ties recorded",
        statewide_cdf="exact <= CDF of band-1 values at each group's mean; changes order of operations AND ties (right CDF versus received histogram mid-bin ranks)",
        area_weighting="WGS84 geodesic area of each native pixel's four corners; near-equal areas locally",
        observations="Descriptive analysis, no probability calibration or predictive validation. Areas approximated by pixel counts except explicitly area-weighted means."))
    print(f"Análise concluída: {OUTPUT}",flush=True)
