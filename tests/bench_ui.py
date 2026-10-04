"""Mesure du coût du rendu dans le navigateur : chargement, page en pause, relecture du monitoring.

Protocole de docs/application.md (section Performances du rendu) : Chromium headless piloté par Playwright,
fenêtre 1920 × 1080, processeur ralenti par les DevTools pour simuler un ordinateur modeste. L'occupation est
la part du temps passée en tâches longues (plus de 50 ms, API Long Tasks) : c'est ce qui rend la page saccadée.
Ce n'est pas un test pytest (nom sans préfixe test_) : il demande une app lancée et un navigateur.

Usage   : make bench-ui                                 (app sur http://127.0.0.1:8050, par make app ou make docker-run)
          uv run --with playwright python tests/bench_ui.py http://127.0.0.1:8050 [autre_url ...]
Prérequis : navigateur de Playwright installé une fois (uvx playwright install chromium)
"""

import asyncio
import sys

from playwright.async_api import async_playwright

RATES = (1, 4)  # processeur normal, puis ralenti 4 fois
SETTLE_MS = {1: 5000, 4: 12000}  # attente de la fin du chargement
WINDOW_MS = 8000  # durée de chaque mesure
LONG_TASKS = (
    "window.__long=[];new PerformanceObserver(l=>l.getEntries().forEach(e=>window.__long.push(e.duration)))"
    ".observe({type:'longtask',buffered:true});"
)

# Mesures -------------------------------------------------------------------------------------------


async def busy(page, ms: int) -> tuple[float, float]:
    """Part du temps en tâches longues sur une fenêtre de ms millisecondes, et plus long gel (ms)."""
    await page.evaluate("window.__long=[]")
    await page.wait_for_timeout(ms)
    tasks = await page.evaluate("window.__long")
    return sum(tasks) / ms, max(tasks or [0])


async def measure(p, url: str, rate: int) -> dict:
    browser = await p.chromium.launch()
    page = await browser.new_page(viewport={"width": 1920, "height": 1080})
    await page.add_init_script(LONG_TASKS)
    cdp = await page.context.new_cdp_session(page)
    await cdp.send("Emulation.setCPUThrottlingRate", {"rate": rate})
    await page.goto(url, wait_until="load", timeout=60000)
    await page.wait_for_selector("#live-video", timeout=60000)
    await page.wait_for_timeout(SETTLE_MS[rate])
    tasks = await page.evaluate("window.__long")
    load = (sum(tasks), max(tasks or [0]))
    # Pause réelle : « Lecture auto » coupée (sinon la vidéo repart), vidéo arrêtée.
    await page.evaluate(
        "(() => { const s = document.getElementById('prod-mode'); if (s.checked) s.click();"
        " document.getElementById('live-video').pause(); })()"
    )
    await page.wait_for_timeout(1500)
    pause = await busy(page, WINDOW_MS // 2)
    await page.evaluate("void document.getElementById('live-video').play()")
    play = await busy(page, WINDOW_MS)
    await browser.close()
    return {"load": load, "pause": pause, "play": play}


# Point d'entrée ------------------------------------------------------------------------------------


async def main(urls: list[str]) -> None:
    async with async_playwright() as p:
        for rate in RATES:
            for url in urls:
                m = await measure(p, url, rate)
                print(
                    f"CPU /{rate}  {url}\n"
                    f"   chargement : {m['load'][0]:6.0f} ms de calcul, plus long gel {m['load'][1]:5.0f} ms\n"
                    f"   en pause   : occupé {m['pause'][0]:4.0%}\n"
                    f"   relecture  : occupé {m['play'][0]:4.0%}, plus long gel {m['play'][1]:4.0f} ms",
                    flush=True,
                )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or ["http://127.0.0.1:8050"]))
