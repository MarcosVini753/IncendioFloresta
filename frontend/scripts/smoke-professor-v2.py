"""Conferência breve da interface v2 com os produtos reais, sem testes de precisão de clique."""
import argparse
import json
import re
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect


def run(url):
    with urlopen(url + "/data/risk/v2/2025/aggregated/manifest.json") as response:
        manifest = json.load(response)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(15000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        select = page.get_by_role("combobox", name="Modelo de risco", exact=True)
        expect(select).to_have_value("random_forest")
        expect(page.get_by_role("button", name="Todas + histórico de queimadas", exact=True)).to_have_class("active")
        for scenario in manifest["scenarios"]:
            page.get_by_role("button", name=scenario["label"], exact=True).click()
            for model in manifest["models"]:
                select.select_option(model["id"])
                metrics = manifest["evaluation"]["historical_test_2025"][scenario["id"]][model["id"]]
                expect(page.locator('[data-metric="roc-auc"]')).to_have_text(f'{metrics["roc_auc"]:.3f}'.replace(".", ","))
                expect(page.locator('[data-metric="average-precision"]')).to_have_text(f'{metrics["pr_auc"]:.6f}'.replace(".", ","))
        page.get_by_role("button", name="Todas + histórico de queimadas", exact=True).click()
        select.select_option("random_forest")
        canvas = page.locator(".maplibregl-canvas")
        expect(canvas).to_be_visible()
        page.wait_for_timeout(1500)
        box = canvas.bounding_box()
        position = {"x": box["width"] * 0.5, "y": box["height"] * 0.5}
        for x, y in [(0.5, 0.5), (0.55, 0.55), (0.45, 0.55)]:
            canvas.click(position={"x": box["width"] * x, "y": box["height"] * y})
            if page.locator(".model-score-list > div").count() == 4:
                position = {"x": box["width"] * x, "y": box["height"] * y}
                break
        expect(page.locator(".model-score-list > div")).to_have_count(4)
        assert "%" not in page.locator(".active-score strong").inner_text()
        expect(page.locator(".active-score")).to_contain_text("Escore do modelo")
        scars = page.get_by_role("checkbox", name="Cicatrizes observadas · 2025")
        scars.uncheck()
        expect(page.locator(".risk-scar-legend")).to_have_count(0)
        scars.check()
        expect(page.locator(".risk-scar-legend")).to_be_visible()
        for _ in range(5):
            close = page.locator(".maplibregl-popup-close-button")
            if close.count():
                close.click()
            canvas.dblclick(position=position)
            page.wait_for_timeout(300)
        expect(page.locator(".map-prototype-note")).to_contain_text("células científicas visíveis", timeout=30000)
        # A resposta dos setores chega antes de o worker do MapLibre renderizar
        # a nova fonte. Não clicar enquanto a camada ainda está sendo desenhada.
        page.wait_for_timeout(1500)
        for x, y in [(0.5, 0.5), (0.55, 0.55), (0.45, 0.55)]:
            canvas.click(position={"x": box["width"] * x, "y": box["height"] * y})
            page.wait_for_timeout(250)
            if "Célula científica original" in page.locator(".cell-details").inner_text():
                break
        expect(page.locator(".cell-details")).to_contain_text("Célula científica original")
        expect(page.locator(".model-score-list > div")).to_have_count(4)
        page.get_by_role("button", name="Clima e cicatrizes · 2025", exact=True).click()
        slider = page.get_by_role("slider")
        expect(slider).to_have_attribute("max", "364")
        slider.focus()
        slider.press("Home")
        expect(slider).to_have_value("0")
        slider.press("End")
        expect(slider).to_have_value("364")
        assert not errors, errors
        browser.close()
        print(json.dumps({"browser": "passed", "combinations": 16, "aggregated_native": "passed", "scars": "passed", "climate": "passed", "page_errors": errors}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    run(parser.parse_args().url.rstrip("/"))
