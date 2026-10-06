"""Smoke real de navegador. Instale playwright no Python e seu Chromium."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

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
        page.locator(".maplibregl-canvas").wait_for(timeout=30000)
        # The map's initial fit triggers after the style has loaded.
        zoom = page.get_by_role("button", name="Zoom in", exact=True)
        zoom.wait_for(timeout=30000)
        page.wait_for_timeout(6000)
        canvas = page.locator(".maplibregl-canvas")
        box = canvas.bounding_box()
        for fx, fy in [(0.5, 0.5), (0.5, 0.65), (0.6, 0.6), (0.4, 0.5)]:
            canvas.click(position={"x": box["width"] * fx, "y": box["height"] * fy})
            if not page.locator(".cell-details-empty").count():
                break
        assert not page.locator(".cell-details-empty").count(), "Célula agregada não selecionada"
        expect(page.locator(".model-score-list > div")).to_have_count(5)
        data_requests = len([u for u in requests if "/data/" in u])
        cell_id = page.locator(".cell-details h2").inner_text()
        for scenario in ["Acre inteiro", "Oeste–Leste"]:
            page.get_by_role("button", name=scenario, exact=True).click()
            for model in ["gradboost", "random_forest", "logistic_regression", "fuzzy_knn", "xgboost"]:
                selector.select_option(model)
                expect(page.locator(".cell-details h2")).to_have_text(cell_id)
                expect(page.locator(".model-score-list > div")).to_have_count(5)
        assert len([u for u in requests if "/data/" in u]) == data_requests, "Troca local gerou requisição de dados"
        selector.select_option("random_forest")
        page.screenshot(path="/tmp/incendio-risk-2025.png", full_page=True)
        for _ in range(5):
            zoom.click()
            page.wait_for_timeout(500)
        expect(page.locator(".map-prototype-note")).to_contain_text("células científicas visíveis", timeout=45000)
        assert any("/sectors/" in u for u in requests), "Grade original não foi carregada"
        # Source processing/rendering happens after the fetch counter is updated.
        page.wait_for_timeout(1500)
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
        # Rapid pan/zoom exercises cancellation and reuse of sectors.
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] / 2 + 120, box["y"] + box["height"] / 2, steps=3)
        page.mouse.up()
        for _ in range(6):
            page.get_by_role("button", name="Zoom out", exact=True).click()
            page.wait_for_timeout(500)
        expect(page.locator(".map-prototype-note")).to_contain_text("Visualização agregada", timeout=30000)
        page.get_by_role("button", name="Clima e cicatrizes · 2025", exact=True).click()
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
        body = page.locator("body").inner_text()
        assert "INPE" not in body and "Perigo" not in body and "Alerta" not in body
        assert not errors, errors
        assert not console_errors, console_errors
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
        print(json.dumps({"browser": "passed", "public_http_200": len(files) + 1,
                          "application_errors": errors, "console_errors": console_errors,
                          "screenshots": ["/tmp/incendio-risk-2025.png", "/tmp/incendio-native-2025.png", "/tmp/incendio-climate-2025.png"]}))
        browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:4173")
    parser.add_argument("--executable")
    args = parser.parse_args()
    main(args.url.rstrip("/"), args.executable)
