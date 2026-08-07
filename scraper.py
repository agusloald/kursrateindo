#!/usr/bin/env python3
"""
scraper.py — refreshes rates.json for the Papan Kurs webpage.

Where the numbers come from:
  - BCA, BNI, Mandiri, Jago, SMBCI (Jenius) -> scraped directly from each
    bank's own official rate page (plain HTML, no login needed).
  - OCBC -> also scraped from its official page, but that page only
    fills in its rate table via JavaScript, so a plain HTTP request sees
    nothing. scrape_ocbc_official() instead drives a real (headless)
    browser via Playwright to load the page properly before reading it.
"""

import json
import re
import sys
from datetime import date

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None  # only needed for scrape_ocbc_official()

CURRENCIES = ["USD", "EUR", "SGD", "JPY", "CNY"]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; rate-board-script/1.0)"}

# Indonesian bank pages list RMB as "CNH" (offshore yuan), not "CNY".
# We match CNH on the page but store/display it as CNY everywhere.
CURRENCY_ALIASES = {"CNH": "CNY"}


def normalize_ccy(text):
    """Extract a 3-letter currency code from text and map it to our
    canonical CURRENCIES list (handles the CNH -> CNY rename). Returns
    None if it's not a currency we track."""
    m = re.search(r"\b([A-Z]{3})\b", text.upper())
    if not m:
        return None
    code = CURRENCY_ALIASES.get(m.group(1), m.group(1))
    return code if code in CURRENCIES else None


def parse_number(text):
    """Turn '20.617,57' or '20,617.57' -> 20617.57"""
    cleaned = text.strip()
    if re.search(r",\d{1,2}$", cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


# ---------------------------------------------------------------------
# Official bank pages — plain HTML tables, scraped directly
# ---------------------------------------------------------------------

def scrape_bca_official():
    url = "https://www.bca.co.id/en/informasi/kurs"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    rates = {}
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        ccy_text = cells[0].get_text(" ", strip=True)
        ccy = normalize_ccy(ccy_text)
        if not ccy:
            continue
        beli = parse_number(cells[1].get_text())
        jual = parse_number(cells[2].get_text())
        if beli is not None and jual is not None:
            rates[ccy] = {"beli": beli, "jual": jual}

    return date.today().isoformat(), rates


def scrape_bni_official():
    url = "https://www.bni.co.id/id-id/beranda/informasi-valas"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    rates = {}
    first_table = soup.find("table") 
    if first_table:
        for row in first_table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            ccy_text = cells[0].get_text(strip=True)
            ccy = normalize_ccy(ccy_text)
            if not ccy:
                continue
            beli = parse_number(cells[1].get_text())
            jual = parse_number(cells[2].get_text())
            if beli is not None and jual is not None:
                rates[ccy] = {"beli": beli, "jual": jual}

    return date.today().isoformat(), rates


def scrape_mandiri_official():
    url = "https://www.bankmandiri.co.id/en/kurs"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    rates = {}
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        ccy_text = cells[0].get_text(strip=True)
        ccy = normalize_ccy(ccy_text)
        if not ccy:
            continue
        beli = parse_number(cells[1].get_text())
        jual = parse_number(cells[2].get_text())
        if beli is not None and jual is not None:
            rates[ccy] = {"beli": beli, "jual": jual}

    return date.today().isoformat(), rates


def scrape_jago_official():
    """Jago provides a clean HTML table for their Foreign Currency Pocket rates."""
    url = "https://www.jago.com/en/jago/digital/pocket/foreign-currency"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    rates = {}
    table = soup.find("table")
    if table:
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 3:
                continue
            ccy_text = cells[0].get_text(" ", strip=True)
            ccy = normalize_ccy(ccy_text)
            if not ccy:
                continue
            # Column 1 is "Customer Sells" (Bank Buys -> Beli)
            beli = parse_number(cells[1].get_text())
            # Column 2 is "Customer Buys" (Bank Sells -> Jual)
            jual = parse_number(cells[2].get_text())
            
            if beli is not None and jual is not None:
                rates[ccy] = {"beli": beli, "jual": jual}

    return date.today().isoformat(), rates


# ---------------------------------------------------------------------
# Jenius (via SMBCI, its parent bank) — plain HTML table
# ---------------------------------------------------------------------

def scrape_smbci_official():
    """SMBC Indonesia (which operates Jenius) prints one simple table:
    Currency | Buy | Sell — and it already labels RMB as CNY directly."""
    url = "https://www.smbci.com/en/prime-lending-rate/kurs"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    rates = {}
    table = soup.find("table")
    if table:
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 3:
                continue
            ccy_text = cells[0].get_text(strip=True)
            ccy = normalize_ccy(ccy_text)
            if not ccy:
                continue
            beli = parse_number(cells[1].get_text())
            jual = parse_number(cells[2].get_text())
            if beli is not None and jual is not None:
                rates[ccy] = {"beli": beli, "jual": jual}

    return date.today().isoformat(), rates


# ---------------------------------------------------------------------
# OCBC — needs a real (headless) browser, since the rate table is
# filled in by JavaScript after the page loads. Requires:
#   pip install playwright --break-system-packages
#   playwright install --with-deps chromium
# ---------------------------------------------------------------------

def scrape_ocbc_official():
    if sync_playwright is None:
        raise RuntimeError(
            "playwright isn't installed — run: pip install playwright "
            "--break-system-packages && playwright install --with-deps chromium"
        )

    url = "https://www.ocbc.id/en/kurs"
    rates = {}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        # Give any late-loading widgets a moment to render.
        page.wait_for_timeout(2000)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 3:
            continue
        ccy_text = cells[0].get_text(" ", strip=True)
        ccy = normalize_ccy(ccy_text)
        if not ccy:
            continue
        beli = parse_number(cells[1].get_text())
        jual = parse_number(cells[2].get_text())
        if beli is not None and jual is not None:
            rates[ccy] = {"beli": beli, "jual": jual}

    return date.today().isoformat(), rates


BANKS = [
    ("BCA",     "Bank Central Asia",      scrape_bca_official),
    ("BNI",     "Bank Negara Indonesia",  scrape_bni_official),
    ("Mandiri", "Bank Mandiri",           scrape_mandiri_official),
    ("Jago",    "Bank Jago",              scrape_jago_official),
    ("Jenius",  "Bank BTPN (Jenius)",     scrape_smbci_official),
    ("OCBC",    "Bank OCBC NISP",         scrape_ocbc_official),
]


def main():
    banks_out = []
    for short_name, full_name, fn in BANKS:
        try:
            bank_date, rates = fn()
        except Exception as e:
            print(f"  ! failed to fetch {short_name}: {e}", file=sys.stderr)
            continue

        if not rates:
            print(f"  ! no rates parsed for {short_name}, skipping", file=sys.stderr)
            continue

        banks_out.append({
            "name": short_name,
            "full": full_name,
            "date": bank_date,
            "rates": rates,
        })
        print(f"  ok {short_name}: {list(rates.keys())}")

    output = {
        "updated": date.today().isoformat(),
        "currencies": CURRENCIES,
        "banks": banks_out,
    }

    with open("rates.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nWrote rates.json with {len(banks_out)} banks.")


if __name__ == "__main__":
    main()