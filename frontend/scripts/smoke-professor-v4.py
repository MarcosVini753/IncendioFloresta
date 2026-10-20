"""Conferência breve da v4 real: HTTP, seleção, pixel original, clima e erros JS."""

import argparse
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

import rasterio
from rasterio.windows import Window
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]


def pt_number(value):
    return float(value.replace(".", "").replace(",", ".").replace("%", "").strip())


def run(url):
    base = url + "/data/risk/v4/2026/"
    with urlopen(base + "manifest.json") as response:
        manifest = json.load(response)
    with urlopen(base + "index.json") as response:
        index = json.load(response)
    for entry in index["sectors"]:
        with urlopen(Request(base + entry["url"], method="HEAD")) as response:
            assert (
                response.status == 200
                and int(response.headers["Content-Length"]) == entry["bytes"]
            ), entry["id"]
    with urlopen(
        Request(base + index["sectors"][0]["url"], headers={"Range": "bytes=0-15"})
    ) as response:
        range_status = response.status
        response.read(16)
    with sync_playwright() as p:
        executable = Path(p.chromium.executable_path)
        if not executable.exists():
            alternatives = sorted(
                Path.home().glob(
                    ".cache/ms-playwright/chromium-*/chrome-linux64/chrome"
                )
            )
            executable = alternatives[-1] if alternatives else executable
        browser = p.chromium.launch(
            executable_path=str(executable),
            args=[
                "--no-sandbox",
                "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader",
            ],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.set_default_timeout(15000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        expect(
            page.get_by_role("button", name="Random Forest", exact=True)
        ).to_have_attribute("aria-pressed", "true")
        expect(
            page.get_by_role(
                "checkbox", name="Cicatrizes observadas · 2025", exact=True
            )
        ).not_to_be_checked()
        canvas = page.locator(".maplibregl-canvas")
        expect(canvas).to_be_visible()
        page.wait_for_timeout(1800)
        bounds = canvas.bounding_box()
        centre = {"x": bounds["width"] * 0.5, "y": bounds["height"] * 0.5}
        canvas.click(position=centre)
        expect(page.locator(".risk-class-shares")).to_be_visible()
        expect(page.locator(".model-score-list > div")).to_have_count(2)
        page.get_by_role("button", name="XGBoost", exact=True).click()
        expect(page.locator(".active-score")).to_contain_text("não calibrado")
        page.get_by_role("button", name="Random Forest", exact=True).click()
        for _ in range(4):
            page.locator(".maplibregl-ctrl-zoom-in").click()
            page.wait_for_timeout(180)
        page.wait_for_timeout(1200)
        canvas.click(position=centre)
        expect(page.locator(".cell-details")).to_contain_text(
            "Pixel científico original"
        )
        row = int(
            page.locator(".cell-metrics div")
            .filter(has_text="Linha original")
            .locator("dd")
            .inner_text()
        )
        column = int(
            page.locator(".cell-metrics div")
            .filter(has_text="Coluna original")
            .locator("dd")
            .inner_text()
        )
        for model, name in enumerate(("RandomForest", "XGBoost")):
            path = (
                ROOT
                / "entrega_professor_v4/mapas_geotiff"
                / f"risco_30m_{name}_AB30C_suave_2026.tif"
            )
            with rasterio.open(path) as source:
                expected = source.read(window=Window(column, row, 1, 1))[:, 0, 0]
            panel = page.locator(".model-score-list > div").nth(model)
            shown_percentile = pt_number(panel.locator("strong").inner_text())
            shown_value = pt_number(
                panel.locator("small").first.inner_text().split("·")[1]
            )
            assert abs(shown_percentile - float(expected[1])) <= 0.051
            assert abs(shown_value - float(expected[0])) <= 0.00000051
        popup = page.locator(".maplibregl-popup-close-button")
        if popup.count():
            popup.click()
        canvas.hover(position=centre)
        page.mouse.down()
        page.mouse.move(
            bounds["x"] + centre["x"] + 100, bounds["y"] + centre["y"] + 40, steps=3
        )
        page.mouse.up()
        page.get_by_role("button", name="XGBoost", exact=True).click()
        page.wait_for_timeout(1000)
        expect(page.locator(".map-prototype-note")).not_to_contain_text("Falha")
        page.screenshot(path="/tmp/incendio-v4-native.png")
        for _ in range(4):
            page.locator(".maplibregl-ctrl-zoom-out").click()
            page.wait_for_timeout(180)
        expect(page.locator(".map-prototype-note")).to_contain_text("Grupos de 5 km")
        scars = page.get_by_role(
            "checkbox", name="Cicatrizes observadas · 2025", exact=True
        )
        scars.check()
        expect(page.locator(".temporal-warning")).to_contain_text(
            "Risco anual: 2026 · Cicatrizes observadas: 2025"
        )
        scars.uncheck()
        page.get_by_role("button", name=re.compile("Clima e cicatrizes · 2025")).click()
        slider = page.get_by_role("slider")
        expect(slider).to_have_attribute("max", "364")
        slider.focus()
        slider.press("Home")
        expect(slider).to_have_value("0")
        slider.press("End")
        expect(slider).to_have_value("364")
        page.get_by_role("button", name=re.compile("Risco · 2026")).click()
        expect(
            page.get_by_role("button", name="XGBoost", exact=True)
        ).to_have_attribute("aria-pressed", "true")
        expect(page.locator(".map-prototype-note")).to_contain_text("Grupos de 5 km")
        assert not errors, errors
        browser.close()
    print(
        json.dumps(
            {
                "browser": "passed",
                "http_sectors": len(index["sectors"]),
                "range_status": range_status,
                "pixel_checked": [row, column],
                "models": 2,
                "climate_extremes": "passed",
                "page_errors": errors,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    run(parser.parse_args().url.rstrip("/"))
