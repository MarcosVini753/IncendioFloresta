"""Smoke real de navegador. Instale playwright no Python e seu Chromium."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

def position_in_fitted_map(bounds, box, coordinates):
    """Projeção da vista inicial: Mercator, sem rotação, padding de 44 px."""
    def mercator(coordinate):
        longitude, latitude = coordinate
        radians = math.radians(latitude)
        return (longitude + 180) / 360, (1 - math.asinh(math.tan(radians)) / math.pi) / 2

    west, south, east, north = bounds
    left, top = mercator([west, north])
    right, bottom = mercator([east, south])
    x, y = mercator(coordinates)
    scale = min((box["width"] - 88) / (right - left), (box["height"] - 88) / (bottom - top))
    return {"x": box["width"] / 2 + (x - (left + right) / 2) * scale,
            "y": box["height"] / 2 + (y - (top + bottom) / 2) * scale}

def main(url, executable):
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable, headless=True,
            args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1100}, ignore_https_errors=True)
        page = context.new_page()
        errors = []
        console_errors = []
        requests = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("request", lambda request: requests.append(request.url))
        page.goto(url, wait_until="domcontentloaded")
        selector = page.locator("#susceptibility-model")
        expect(selector).to_have_value("random_forest", timeout=30000)
        expect(page.get_by_role("button", name="Oeste–Leste", exact=True)).to_have_class("active")
        expect(selector.locator("option")).to_have_count(5)
        annual_scars = page.get_by_role("checkbox", name="Cicatrizes observadas · 2025", exact=True)
        expect(annual_scars).to_be_checked()
        expect(page.locator(".risk-scar-control small")).to_contain_text("59 pixels classificados", timeout=30000)
        expect(page.locator(".risk-scar-legend")).to_be_visible()
        manifest = page.request.get(url + "/data/risk/v1/2025/aggregated/manifest.json").json()
        expect(page.locator('[data-metric="top10"]')).to_have_text("11 de 39")
        page.get_by_text("Outros cortes e leitura das métricas", exact=True).click()
        expect(page.locator(".evaluation-priority-table tbody tr")).to_have_count(4)
        page.locator(".maplibregl-canvas").wait_for(timeout=30000)
        # The map's initial fit triggers after the style has loaded.
        zoom = page.get_by_role("button", name="Zoom in", exact=True)
        zoom.wait_for(timeout=30000)
        page.wait_for_timeout(6000)
        canvas = page.locator(".maplibregl-canvas")
        box = canvas.bounding_box()
        scars = page.request.get(url + "/data/climate/v1/2025/scars.geojson").json()
        scar_positions = [(scar, position_in_fitted_map(manifest["bounds"], box, scar["properties"]["center"]))
                          for scar in scars["features"]]
        # Marcadores de pixels vizinhos podem se sobrepor no zoom estadual.
        isolated_scars = [pair for i, pair in enumerate(scar_positions)
                          if all(math.hypot(pair[1]["x"] - other[1]["x"], pair[1]["y"] - other[1]["y"]) > 12
                                 for j, other in enumerate(scar_positions) if i != j)]
        assert isolated_scars, "Nenhum marcador isolado para conferir a data por clique"
        scar, scar_position = min(
            isolated_scars,
            key=lambda pair: (pair[1]["x"] - box["width"] / 2)**2 + (pair[1]["y"] - box["height"] / 2)**2,
        )
        canvas.click(position=scar_position)
        expect(page.locator(".maplibregl-popup-content")).to_contain_text("Cicatriz observada · 2025")
        expect(page.locator(".maplibregl-popup-content")).to_contain_text("/".join(reversed(scar["properties"]["date"].split("-"))))
        expect(page.locator(".maplibregl-popup-content")).to_contain_text("escore relativo")
        page.locator(".maplibregl-popup-close-button").click()
        for fx, fy in [(0.5, 0.5), (0.5, 0.65), (0.6, 0.6), (0.4, 0.5)]:
            canvas.click(position={"x": box["width"] * fx, "y": box["height"] * fy})
            if not page.locator(".cell-details-empty").count():
                break
        assert not page.locator(".cell-details-empty").count(), "Célula agregada não selecionada"
        expect(page.locator(".model-score-list > div")).to_have_count(5)
        data_requests = len([u for u in requests if "/data/" in u])
        annual_scars.uncheck()
        expect(page.locator(".risk-scar-legend")).to_have_count(0)
        annual_scars.check()
        cell_id = page.locator(".cell-details h2").inner_text()
        for scenario in ["Acre inteiro", "Oeste–Leste"]:
            page.get_by_role("button", name=scenario, exact=True).click()
            for model in ["gradboost", "random_forest", "logistic_regression", "fuzzy_knn", "xgboost"]:
                selector.select_option(model)
                expect(page.locator(".cell-details h2")).to_have_text(cell_id)
                expect(page.locator(".model-score-list > div")).to_have_count(5)
                scenario_id = "unico" if scenario == "Acre inteiro" else "regional"
                metrics = manifest["evaluation"]["historical_test_2025"][scenario_id][model]
                found = round(metrics["det@10%"] * manifest["evaluation"]["test_positive_cells"])
                expect(page.locator('[data-metric="top10"]')).to_have_text(f"{found} de 39")
                expect(page.locator('[data-metric="roc-auc"]')).to_have_text(f'{metrics["roc_auc"]:.3f}'.replace(".", ","))
                expect(page.locator('[data-metric="average-precision"]')).to_have_text(f'{metrics["pr_auc"]:.6f}'.replace(".", ","))
        assert len([u for u in requests if "/data/" in u]) == data_requests, "Troca local gerou requisição de dados"
        selector.select_option("random_forest")
        page.screenshot(path="/tmp/incendio-risk-2025.png", full_page=True)
        # Aproximar sobre a cicatriz mantém o pixel próximo à posição inicial.
        for _ in range(5):
            if page.locator(".maplibregl-popup-close-button").count():
                page.locator(".maplibregl-popup-close-button").click()
            canvas.dblclick(position=scar_position)
            page.wait_for_timeout(500)
        expect(page.locator(".map-prototype-note")).to_contain_text("células científicas visíveis", timeout=45000)
        assert any("/sectors/" in u for u in requests), "Grade original não foi carregada"
        # Source processing/rendering happens after the fetch counter is updated.
        page.wait_for_timeout(1500)
        # O arredondamento dos eventos de ponteiro é ampliado pelo zoom.
        # Procurar o polígono numa pequena vizinhança da posição prevista.
        found_native_scar = False
        offsets = [0, -4, 4, -8, 8, -12, 12, -16, 16, -20, 20, -24, 24]
        for dx in offsets:
            for dy in offsets:
                if page.locator(".maplibregl-popup-close-button").count():
                    page.locator(".maplibregl-popup-close-button").click()
                canvas.click(position={"x": scar_position["x"] + dx, "y": scar_position["y"] + dy})
                if "Cicatriz observada · 2025" in (page.locator(".maplibregl-popup-content").text_content() or ""):
                    found_native_scar = True
                    break
            if found_native_scar:
                break
        assert found_native_scar, "Polígono da cicatriz não encontrado na grade original"
        expect(page.locator(".maplibregl-popup-content")).to_contain_text("Cicatriz observada · 2025")
        expect(page.locator(".maplibregl-popup-content")).to_contain_text("/".join(reversed(scar["properties"]["date"].split("-"))))
        expect(page.locator(".cell-details .eyebrow").first).to_have_text("Célula científica original")
        page.screenshot(path="/tmp/incendio-native-2025.png", full_page=True)
        for fx, fy in [(0.5, 0.5), (0.5, 0.65), (0.6, 0.6), (0.4, 0.5)]:
            if page.locator(".maplibregl-popup-close-button").count():
                page.locator(".maplibregl-popup-close-button").click()
            canvas.click(position={"x": box["width"] * fx, "y": box["height"] * fy})
            page.wait_for_timeout(300)
            if page.locator(".cell-details .eyebrow").first.inner_text().strip() == "Célula científica original":
                break
        expect(page.locator(".cell-details .eyebrow").first).to_have_text("Célula científica original")
        expect(page.locator(".cell-details")).to_contain_text("Índice X")
        expect(page.locator('[data-metric="top10"]')).to_have_text("11 de 39")
        expect(page.locator(".risk-scar-legend")).to_be_visible()
        # Rapid pan/zoom exercises cancellation and reuse of sectors.
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] / 2 + 120, box["y"] + box["height"] / 2, steps=3)
        page.mouse.up()
        for _ in range(6):
            page.get_by_role("button", name="Zoom out", exact=True).click()
            page.wait_for_timeout(500)
        expect(page.locator(".map-prototype-note")).to_contain_text("Visualização agregada", timeout=30000)
        annual_scars.uncheck()
        page.get_by_role("button", name="Clima e cicatrizes · 2025", exact=True).click()
        expect(page.get_by_role("checkbox")).to_be_checked()
        slider = page.get_by_role("slider", name="Selecionar data")
        expect(slider).to_have_attribute("max", "364", timeout=30000)
        expect(slider).to_have_value("236")
        slider.fill("0")
        expect(page.locator(".timeline-header strong")).to_have_text("01/01/2025")
        expect(page.get_by_role("button", name="Dia anterior")).to_be_disabled()
        slider.fill("364")
        expect(page.locator(".timeline-header strong")).to_have_text("31/12/2025")
        expect(page.get_by_role("button", name="Próximo dia")).to_be_disabled()
        page.get_by_role("button", name="Precipitação", exact=True).click()
        page.get_by_role("checkbox").uncheck()
        slider.fill("236")
        page.wait_for_timeout(1500)
        canvas = page.locator(".maplibregl-canvas")
        box = canvas.bounding_box()
        for fx, fy in [(0.5, 0.5), (0.5, 0.65), (0.6, 0.6), (0.4, 0.5)]:
            canvas.click(position={"x": box["width"] * fx, "y": box["height"] * fy})
            if not page.locator(".cell-details-empty").count():
                break
        expect(page.get_by_label("Série climática anual")).to_be_visible()
        expect(page.locator(".recharts-line-curve")).to_have_count(3)
        assert all(len(value or "") > 500 for value in page.locator(".recharts-line-curve").evaluate_all("(nodes) => nodes.map((node) => node.getAttribute('d'))"))
        page.screenshot(path="/tmp/incendio-climate-2025.png", full_page=True)
        page.get_by_role("button", name="Risco", exact=True).click()
        expect(page.locator("#susceptibility-model")).to_have_value("random_forest")
        expect(page.get_by_role("button", name="Oeste–Leste", exact=True)).to_have_class("active")
        annual_scars = page.get_by_role("checkbox", name="Cicatrizes observadas · 2025", exact=True)
        expect(annual_scars).not_to_be_checked()
        annual_scars.check()
        expect(page.locator(".risk-scar-legend")).to_be_visible()
        expect(page.locator('[data-metric="top10"]')).to_have_text("11 de 39")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Overflow horizontal no celular"
        page.screenshot(path="/tmp/incendio-risk-evaluation-mobile.png", full_page=True)
        body = page.locator("body").inner_text()
        assert "INPE" not in body and "Perigo" not in body and "Alerta" not in body
        assert not errors, errors
        assert not console_errors, console_errors
        # Uma falha nas observações não deve bloquear mapa ou avaliação do Risco.
        retry_page = context.new_page()
        retry_errors = []
        retry_page.on("pageerror", lambda error: retry_errors.append(str(error)))
        fail_scars = True
        def handle_scars(route):
            if fail_scars:
                route.fulfill(status=503, body="Indisponível")
            else:
                route.continue_()
        retry_page.route("**/data/climate/v1/2025/scars.geojson", handle_scars)
        retry_page.goto(url, wait_until="domcontentloaded")
        expect(retry_page.get_by_role("alert")).to_contain_text("HTTP 503", timeout=30000)
        expect(retry_page.locator('[data-metric="top10"]')).to_have_text("11 de 39", timeout=30000)
        expect(retry_page.locator("#susceptibility-model")).to_have_value("random_forest")
        fail_scars = False
        retry_page.get_by_role("button", name="Tentar novamente", exact=True).click()
        expect(retry_page.locator(".risk-scar-control small")).to_contain_text("59 pixels classificados", timeout=30000)
        expect(retry_page.get_by_role("alert")).to_have_count(0)
        assert not retry_errors, retry_errors
        retry_page.close()
        index_response = page.request.get(url + "/data/risk/v1/2025/native_sharded_grid/index.json")
        assert index_response.status == 200
        index = index_response.json()
        files = ["/data/risk/v1/2025/aggregated/manifest.json",
                 "/data/risk/v1/2025/aggregated/mapa.geojson",
                 "/data/risk/v1/2025/aggregated/limite_acre.geojson",
                 "/data/risk/v1/2025/native_sharded_grid/manifest.json",
                 *["/data/risk/v1/2025/native_sharded_grid/" + e["url"] for e in index["sectors"]],
                 *["/data/climate/v1/2025/" + name for name in
                   ["manifest.json", "grid.geojson", "boundary.geojson", "humidity.json", "precipitation.json", "scars.geojson"]]]
        for file in files:
            response = page.request.head(url + file)
            assert response.status == 200 and "text/html" not in response.headers.get("content-type", ""), file
        print(json.dumps({"browser": "passed", "scar_click_aggregated_native": "passed", "scar_http_retry": "passed", "public_http_200": len(files) + 1,
                          "application_errors": errors, "console_errors": console_errors,
                          "screenshots": ["/tmp/incendio-risk-2025.png", "/tmp/incendio-native-2025.png", "/tmp/incendio-climate-2025.png", "/tmp/incendio-risk-evaluation-mobile.png"]}))
        browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:4173")
    parser.add_argument("--executable")
    args = parser.parse_args()
    main(args.url.rstrip("/"), args.executable)
