"""Optional end-to-end QA: pip install playwright; playwright install chromium.

Run against a locally served deployment base, or the published GitHub Pages URL.
"""
import argparse
import csv
import io
import json
from pathlib import Path
import shutil
from urllib.parse import quote


def check(base, executable=None, screenshots=None):
    from playwright.sync_api import sync_playwright
    base = base.rstrip('/') + '/'
    with sync_playwright() as p:
        options = {'headless': True}
        if executable:
            options['executable_path'] = executable
        browser = p.chromium.launch(**options)
        context = browser.new_context(viewport={'width':1440,'height':1000}, accept_downloads=True)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        response = context.request.get(base + 'data/catalog.json')
        assert response.ok, 'Catalog HTTP failure'
        data = response.json()
        total = len(data['records'])
        page.goto(base, wait_until='networkidle')
        page.wait_for_selector('.survey-row')
        assert page.locator('.survey-row').count() == min(30, total)
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
        if screenshots:
            screenshots.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshots/'desktop-home.png'))
        page.locator('[data-save]').first.click()
        first = page.locator('[data-save]').first.get_attribute('data-save')
        page.reload(wait_until='networkidle')
        assert page.locator(f'[data-save="{first}"]').first.get_attribute('aria-pressed') == 'true'
        page.locator('[data-param="saved"]').check()
        assert page.locator('.survey-row').count() == 1
        page.locator('[data-action="reset"]').first.click()
        # All filtered entries, not just rendered rows, are exported.
        with page.expect_download() as download:
            page.locator('[data-action="export"]').click()
        exported = Path(download.value.path()).read_text(encoding='utf-8-sig')
        assert len(list(csv.reader(io.StringIO(exported)))) == total + 1
        page.goto(base+'library/', wait_until='networkidle')
        page.locator('[data-param="sort"]').select_option('citations')
        expected = sorted(data['records'], key=lambda r:(r['citations'] is None, -(r['citations'] or 0)))[0]['citations']
        first_id = page.locator('.survey-row').first.get_attribute('data-paper')
        assert next(r['citations'] for r in data['records'] if r['id']==first_id) == expected
        cid = data['taxonomy'][0]['id']
        page.locator(f'[data-category="{cid}"]').click()
        assert page.locator('.survey-row').count() == min(30,sum(r['category']==cid for r in data['records']))
        page.locator(f'[data-follow="{cid}"]').click()
        assert page.locator(f'[data-follow="{cid}"]').get_attribute('aria-pressed') == 'true'
        page.go_back(wait_until='networkidle')
        assert 'category=' not in page.url
        page.locator('#search').fill('agent memory')
        page.wait_for_timeout(1200)
        assert 'q=agent' in page.url
        assert page.locator('.survey-row').count() > 0
        page.locator('[data-compare]').nth(0).click()
        page.locator('[data-compare]').nth(1).click()
        ids = page.evaluate('JSON.parse(localStorage.getItem("survey-radar:compare"))')
        assert len(ids) == 2
        page.goto(base+'compare/?ids='+quote(','.join(ids)),wait_until='networkidle')
        assert page.locator('.compare-table thead th').count() == 3
        assert page.locator('.compare-table tbody tr').count() >= 10
        for route in ('trends','coverage','landscape','updates','about'):
            page.goto(base+route+'/', wait_until='networkidle')
            page.wait_for_selector('#app h1')
            assert not page.locator('[role="alert"]').count(), route
            page.set_viewport_size({'width':390,'height':844})
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), route+' mobile overflow'
            page.set_viewport_size({'width':1440,'height':1000})
        page.goto(base+'papers/'+ids[0]+'/',wait_until='networkidle')
        assert page.locator('.detail h1').count() == 1
        assert page.locator('#related .survey-row').count() > 0
        assert page.locator('.provenance').count() == 1
        page.goto(base+'library/',wait_until='networkidle')
        page.locator('#language').click()
        assert page.locator('html').get_attribute('lang') == 'en'
        assert 'Survey library' in page.locator('h1').inner_text()
        page.reload(wait_until='networkidle')
        assert page.locator('html').get_attribute('lang') == 'en'
        page.locator('#language').click()
        page.set_viewport_size({'width':390,'height':844})
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), 'library mobile overflow'
        if screenshots:
            page.screenshot(path=str(screenshots/'mobile-library.png'))
        # A failed data request must display a recoverable error, not an empty page.
        page.route('**/data/catalog.json', lambda route: route.abort())
        page.reload(wait_until='networkidle')
        page.wait_for_selector('[role="alert"]')
        page.unroute('**/data/catalog.json')
        page.locator('#retry').click()
        page.wait_for_selector('.survey-row')
        for feed in ('feed.xml','feeds/'+cid+'.xml'):
            assert context.request.get(base+feed).ok, feed
        assert not errors, errors
        print(json.dumps({'status':'PASS','records':total,'checks':'search, facets, sorts, saved persistence, followed categories, history, complete CSV, URL comparison, all routes, detail refresh, EN/ZH, 390px overflow, network recovery, RSS'},ensure_ascii=True))
        browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://localhost:8000')
    parser.add_argument('--browser', default=shutil.which('msedge'))
    parser.add_argument('--screenshots', type=Path)
    args = parser.parse_args()
    check(args.url, args.browser, args.screenshots)
