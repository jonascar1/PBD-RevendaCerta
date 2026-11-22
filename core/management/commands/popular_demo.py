"""Popula a base de demonstração com veículos que tenham fotos do Wikimedia Commons.

Uso: python manage.py popular_demo --limite 3
Requer: requests, Pillow; acesso à internet; usuário gerente ativo existente.
"""
import hashlib
import io
import json
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote, urlparse, urlencode

import requests
from PIL import Image, ImageOps, UnidentifiedImageError
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from core.models import FotoVeiculo, Usuario, Veiculo, LancamentoFinanceiro

# Marca, modelo, tipo, preço aproximado de demonstração (não é cotação FIPE).
CATALOGO = [
    ("Volkswagen", "Golf", "HATCH", 85000),
    ("Honda", "Civic", "SEDA", 105000),
    ("Toyota", "Corolla", "SEDA", 110000),
    ("Ford", "Mustang", "OUTRO", 290000),
    ("Chevrolet", "Camaro", "OUTRO", 260000),
    ("Volkswagen", "Polo", "HATCH", 78000),
    ("Volkswagen", "Jetta", "SEDA", 125000),
    ("Volkswagen", "Tiguan", "SUV", 150000),
    ("Volkswagen", "Passat", "SEDA", 98000),
    ("Honda", "Fit", "HATCH", 65000),
    ("Honda", "HR-V", "SUV", 105000),
    ("Honda", "CR-V", "SUV", 140000),
    ("Toyota", "Yaris", "HATCH", 79000),
    ("Toyota", "Hilux", "PICAPE", 220000),
    ("Toyota", "RAV4", "SUV", 175000),
    ("Chevrolet", "Onix", "HATCH", 65000),
    ("Chevrolet", "Cruze", "SEDA", 88000),
    ("Chevrolet", "Tracker", "SUV", 105000),
    ("Chevrolet", "S10", "PICAPE", 155000),
    ("Ford", "Focus", "HATCH", 70000),
    ("Ford", "Fiesta", "HATCH", 52000),
    ("Ford", "Ranger", "PICAPE", 185000),
    ("Hyundai", "HB20", "HATCH", 72000),
    ("Hyundai", "Creta", "SUV", 112000),
    ("Hyundai", "Tucson", "SUV", 98000),
    ("Nissan", "Sentra", "SEDA", 105000),
    ("Nissan", "Kicks", "SUV", 100000),
    ("Nissan", "Versa", "SEDA", 80000),
    ("Renault", "Sandero", "HATCH", 54000),
    ("Renault", "Duster", "SUV", 85000),
    ('Fiat', 'Argo', 'HATCH', 72000),
    ('Fiat', 'Mobi', 'HATCH', 55000),
    ('Fiat', 'Uno', 'HATCH', 44000),
    ('Fiat', 'Palio', 'HATCH', 39000),
    ('Fiat', 'Punto', 'HATCH', 48000),
    ('Fiat', 'Cronos', 'SEDA', 78000),
    ('Fiat', 'Siena', 'SEDA', 42000),
    ('Fiat', 'Grand Siena', 'SEDA', 50000),
    ('Fiat', 'Toro', 'PICAPE', 145000),
    ('Fiat', 'Strada', 'PICAPE', 105000),
    ('Fiat', 'Fastback', 'SUV', 135000),
    ('Fiat', 'Pulse', 'SUV', 108000),
    ('Fiat', 'Idea', 'UTILITARIO', 42000),
    ('Fiat', 'Doblo', 'UTILITARIO', 65000),
    ('Fiat', 'Fiorino', 'UTILITARIO', 80000),
    ('Volkswagen', 'Gol', 'HATCH', 45000),
    ('Volkswagen', 'Voyage', 'SEDA', 55000),
    ('Volkswagen', 'Virtus', 'SEDA', 105000),
    ('Volkswagen', 'Nivus', 'SUV', 120000),
    ('Volkswagen', 'T-Cross', 'SUV', 135000),
    ('Volkswagen', 'Taos', 'SUV', 165000),
    ('Volkswagen', 'Amarok', 'PICAPE', 210000),
    ('Volkswagen', 'Saveiro', 'PICAPE', 90000),
    ('Volkswagen', 'Fox', 'HATCH', 52000),
    ('Volkswagen', 'Up', 'HATCH', 52000),
    ('Volkswagen', 'Beetle', 'OUTRO', 110000),
    ('Volkswagen', 'Touareg', 'SUV', 210000),
    ('Volkswagen', 'ID.4', 'SUV', 250000),
    ('Chevrolet', 'Celta', 'HATCH', 35000),
    ('Chevrolet', 'Corsa', 'HATCH', 35000),
    ('Chevrolet', 'Classic', 'SEDA', 37000),
    ('Chevrolet', 'Prisma', 'SEDA', 55000),
    ('Chevrolet', 'Spin', 'UTILITARIO', 85000),
    ('Chevrolet', 'Montana', 'PICAPE', 115000),
    ('Chevrolet', 'Equinox', 'SUV', 170000),
    ('Chevrolet', 'Trailblazer', 'SUV', 240000),
    ('Chevrolet', 'Captiva', 'SUV', 80000),
    ('Chevrolet', 'Sonic', 'HATCH', 50000),
    ('Chevrolet', 'Astra', 'HATCH', 40000),
    ('Chevrolet', 'Vectra', 'SEDA', 45000),
    ('Chevrolet', 'Omega', 'SEDA', 55000),
    ('Chevrolet', 'Bolt', 'HATCH', 150000),
    ('Ford', 'Ka', 'HATCH', 47000),
    ('Ford', 'EcoSport', 'SUV', 70000),
    ('Ford', 'Fusion', 'SEDA', 90000),
    ('Ford', 'Edge', 'SUV', 110000),
    ('Ford', 'Territory', 'SUV', 150000),
    ('Ford', 'Bronco', 'SUV', 250000),
    ('Ford', 'Maverick', 'PICAPE', 220000),
    ('Ford', 'F-150', 'PICAPE', 430000),
    ('Ford', 'Explorer', 'SUV', 190000),
    ('Ford', 'Escape', 'SUV', 130000),
    ('Toyota', 'Etios', 'HATCH', 58000),
    ('Toyota', 'Camry', 'SEDA', 190000),
    ('Toyota', 'Prius', 'HATCH', 125000),
    ('Toyota', 'SW4', 'SUV', 300000),
    ('Toyota', 'Corolla Cross', 'SUV', 165000),
    ('Toyota', 'Land Cruiser', 'SUV', 400000),
    ('Toyota', 'C-HR', 'SUV', 160000),
    ('Toyota', 'Supra', 'OUTRO', 460000),
    ('Toyota', 'GR86', 'OUTRO', 280000),
    ('Toyota', 'Sienna', 'UTILITARIO', 240000),
    ('Honda', 'City', 'SEDA', 100000),
    ('Honda', 'WR-V', 'SUV', 92000),
    ('Honda', 'Accord', 'SEDA', 170000),
    ('Honda', 'Pilot', 'SUV', 230000),
    ('Honda', 'Odyssey', 'UTILITARIO', 180000),
    ('Honda', 'Jazz', 'HATCH', 72000),
    ('Honda', 'Prelude', 'OUTRO', 110000),
    ('Honda', 'NSX', 'OUTRO', 800000),
    ('Hyundai', 'HB20S', 'SEDA', 80000),
    ('Hyundai', 'i30', 'HATCH', 68000),
    ('Hyundai', 'Elantra', 'SEDA', 95000),
    ('Hyundai', 'Sonata', 'SEDA', 110000),
    ('Hyundai', 'Santa Fe', 'SUV', 160000),
    ('Hyundai', 'Palisade', 'SUV', 350000),
    ('Hyundai', 'Kona', 'SUV', 180000),
    ('Hyundai', 'Ioniq 5', 'SUV', 310000),
    ('Hyundai', 'Azera', 'SEDA', 110000),
    ('Nissan', 'March', 'HATCH', 48000),
    ('Nissan', 'Tiida', 'HATCH', 45000),
    ('Nissan', 'Livina', 'UTILITARIO', 52000),
    ('Nissan', 'Frontier', 'PICAPE', 175000),
    ('Nissan', 'X-Trail', 'SUV', 145000),
    ('Nissan', 'Qashqai', 'SUV', 130000),
    ('Nissan', 'Leaf', 'HATCH', 130000),
    ('Nissan', 'Altima', 'SEDA', 150000),
    ('Nissan', '370Z', 'OUTRO', 260000),
    ('Nissan', 'GT-R', 'OUTRO', 750000),
    ('Renault', 'Logan', 'SEDA', 53000),
    ('Renault', 'Kwid', 'HATCH', 56000),
    ('Renault', 'Captur', 'SUV', 85000),
    ('Renault', 'Oroch', 'PICAPE', 100000),
    ('Renault', 'Fluence', 'SEDA', 60000),
    ('Renault', 'Megane', 'HATCH', 65000),
    ('Renault', 'Clio', 'HATCH', 38000),
    ('Renault', 'Kardian', 'SUV', 115000),
    ('Renault', 'Koleos', 'SUV', 145000),
    ('Jeep', 'Renegade', 'SUV', 110000),
    ('Jeep', 'Compass', 'SUV', 145000),
    ('Jeep', 'Commander', 'SUV', 220000),
    ('Jeep', 'Wrangler', 'SUV', 310000),
    ('Jeep', 'Grand Cherokee', 'SUV', 260000),
    ('Jeep', 'Gladiator', 'PICAPE', 380000),
    ('Peugeot', '208', 'HATCH', 79000),
    ('Peugeot', '2008', 'SUV', 105000),
    ('Peugeot', '3008', 'SUV', 155000),
    ('Peugeot', '5008', 'SUV', 180000),
    ('Peugeot', '308', 'HATCH', 65000),
    ('Peugeot', '408', 'SEDA', 62000),
    ('Peugeot', '207', 'HATCH', 36000),
    ('Citroen', 'C3', 'HATCH', 69000),
    ('Citroen', 'C4 Cactus', 'SUV', 90000),
    ('Citroen', 'Aircross', 'SUV', 85000),
    ('Citroen', 'C4 Lounge', 'SEDA', 69000),
    ('Citroen', 'C5 Aircross', 'SUV', 170000),
    ('Mitsubishi', 'L200', 'PICAPE', 170000),
    ('Mitsubishi', 'ASX', 'SUV', 100000),
    ('Mitsubishi', 'Outlander', 'SUV', 145000),
    ('Mitsubishi', 'Pajero', 'SUV', 150000),
    ('Mitsubishi', 'Eclipse Cross', 'SUV', 160000),
    ('Mitsubishi', 'Lancer', 'SEDA', 82000),
    ('Suzuki', 'Jimny', 'SUV', 125000),
    ('Suzuki', 'Vitara', 'SUV', 98000),
    ('Suzuki', 'S-Cross', 'SUV', 105000),
    ('Suzuki', 'Swift', 'HATCH', 69000),
    ('Subaru', 'Impreza', 'SEDA', 120000),
    ('Subaru', 'Forester', 'SUV', 145000),
    ('Subaru', 'Outback', 'SUV', 165000),
    ('Subaru', 'WRX', 'SEDA', 220000),
    ('Subaru', 'BRZ', 'OUTRO', 230000),
    ('Kia', 'Picanto', 'HATCH', 60000),
    ('Kia', 'Rio', 'HATCH', 70000),
    ('Kia', 'Cerato', 'SEDA', 95000),
    ('Kia', 'Sportage', 'SUV', 145000),
    ('Kia', 'Sorento', 'SUV', 190000),
    ('Kia', 'Soul', 'SUV', 95000),
    ('Kia', 'Carnival', 'UTILITARIO', 240000),
    ('BMW', '320i', 'SEDA', 210000),
    ('BMW', '330i', 'SEDA', 260000),
    ('BMW', '520i', 'SEDA', 290000),
    ('BMW', 'X1', 'SUV', 205000),
    ('BMW', 'X3', 'SUV', 260000),
    ('BMW', 'X5', 'SUV', 390000),
    ('BMW', 'X6', 'SUV', 450000),
    ('BMW', 'M3', 'SEDA', 650000),
    ('BMW', 'M4', 'OUTRO', 690000),
    ('BMW', 'Z4', 'OUTRO', 370000),
    ('BMW', 'i3', 'HATCH', 165000),
    ('BMW', 'iX', 'SUV', 570000),
    ('Mercedes-Benz', 'A 200', 'HATCH', 195000),
    ('Mercedes-Benz', 'C 180', 'SEDA', 190000),
    ('Mercedes-Benz', 'C 200', 'SEDA', 230000),
    ('Mercedes-Benz', 'E 300', 'SEDA', 340000),
    ('Mercedes-Benz', 'GLA 200', 'SUV', 220000),
    ('Mercedes-Benz', 'GLB 200', 'SUV', 260000),
    ('Mercedes-Benz', 'GLC 300', 'SUV', 370000),
    ('Mercedes-Benz', 'GLE 450', 'SUV', 580000),
    ('Mercedes-Benz', 'CLA 200', 'SEDA', 240000),
    ('Mercedes-Benz', 'AMG GT', 'OUTRO', 800000),
    ('Audi', 'A1', 'HATCH', 110000),
    ('Audi', 'A3', 'SEDA', 165000),
    ('Audi', 'A4', 'SEDA', 205000),
    ('Audi', 'A5', 'OUTRO', 235000),
    ('Audi', 'A6', 'SEDA', 300000),
    ('Audi', 'Q3', 'SUV', 205000),
    ('Audi', 'Q5', 'SUV', 290000),
    ('Audi', 'Q7', 'SUV', 430000),
    ('Audi', 'TT', 'OUTRO', 250000),
    ('Audi', 'R8', 'OUTRO', 950000),
    ('Volvo', 'XC40', 'SUV', 230000),
    ('Volvo', 'XC60', 'SUV', 310000),
    ('Volvo', 'XC90', 'SUV', 420000),
    ('Volvo', 'S60', 'SEDA', 230000),
    ('Volvo', 'S90', 'SEDA', 320000),
    ('Volvo', 'C40', 'SUV', 270000),
    ('Porsche', 'Macan', 'SUV', 420000),
    ('Porsche', 'Cayenne', 'SUV', 550000),
    ('Porsche', 'Panamera', 'SEDA', 680000),
    ('Porsche', '911', 'OUTRO', 900000),
    ('Porsche', '718 Cayman', 'OUTRO', 490000),
    ('Porsche', 'Taycan', 'SEDA', 650000),
    ('Land Rover', 'Defender', 'SUV', 580000),
    ('Land Rover', 'Discovery', 'SUV', 380000),
    ('Land Rover', 'Discovery Sport', 'SUV', 260000),
    ('Land Rover', 'Range Rover Evoque', 'SUV', 290000),
    ('Land Rover', 'Range Rover Sport', 'SUV', 650000),
    ('Mini', 'Cooper', 'HATCH', 165000),
    ('Mini', 'Countryman', 'SUV', 205000),
    ('Mini', 'Clubman', 'HATCH', 185000),
    ('BYD', 'Dolphin', 'HATCH', 145000),
    ('BYD', 'Dolphin Mini', 'HATCH', 115000),
    ('BYD', 'Song Plus', 'SUV', 215000),
    ('BYD', 'Yuan Plus', 'SUV', 220000),
    ('BYD', 'Seal', 'SEDA', 275000),
    ('BYD', 'Han', 'SEDA', 340000),
    ('GWM', 'Haval H6', 'SUV', 200000),
    ('GWM', 'Ora 03', 'HATCH', 155000),
    ('GWM', 'Tank 300', 'SUV', 330000),
    ('Chery', 'Tiggo 2', 'SUV', 70000),
    ('Chery', 'Tiggo 5X', 'SUV', 110000),
    ('Chery', 'Tiggo 7', 'SUV', 140000),
    ('Chery', 'Tiggo 8', 'SUV', 180000),
    ('JAC', 'T40', 'SUV', 70000),
    ('JAC', 'T50', 'SUV', 85000),
    ('JAC', 'T60', 'SUV', 105000),
    ('RAM', '1500', 'PICAPE', 420000),
    ('RAM', '2500', 'PICAPE', 490000),
    ('RAM', 'Rampage', 'PICAPE', 230000),
    ('Mazda', 'Mazda3', 'HATCH', 130000),
    ('Mazda', 'Mazda6', 'SEDA', 150000),
    ('Mazda', 'CX-3', 'SUV', 130000),
    ('Mazda', 'CX-5', 'SUV', 160000),
    ('Mazda', 'MX-5', 'OUTRO', 220000),
    ('Lexus', 'UX 250h', 'SUV', 230000),
    ('Lexus', 'NX 300h', 'SUV', 290000),
    ('Lexus', 'RX 350', 'SUV', 400000),
    ('Lexus', 'ES 300h', 'SEDA', 330000),
    ('Jaguar', 'XE', 'SEDA', 200000),
    ('Jaguar', 'XF', 'SEDA', 250000),
    ('Jaguar', 'F-Pace', 'SUV', 350000),
    ('Jaguar', 'F-Type', 'OUTRO', 490000),
    ('Tesla', 'Model 3', 'SEDA', 290000),
    ('Tesla', 'Model Y', 'SUV', 330000),
    ('Tesla', 'Model S', 'SEDA', 500000),
    ('Tesla', 'Model X', 'SUV', 580000),
]

API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "VendaCertaDemoImporter/1.0 (educational Django demo; contact: vendacerta-demo@example.org)"
# Substitua o e-mail acima por um contato real antes de executar em volume.
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}
def licenca_livre(meta):
    """Aceita CC BY, CC BY-SA, CC0 e domínio público via nome ou URL da licença."""
    nome = re.sub(r"<[^>]+>", "", meta.get("LicenseShortName", {}).get("value", "")).strip()
    url = meta.get("LicenseUrl", {}).get("value", "").lower()
    normalizada = re.sub(r"[\s_-]+", "", nome.lower())
    livre = (normalizada.startswith("ccby") or normalizada.startswith("cc0")
             or normalizada in ("publicdomain", "pd"))
    livre = livre or bool(re.search(r"creativecommons\.org/licenses/by(?:-sa)?/", url))
    livre = livre or "creativecommons.org/publicdomain/zero/" in url
    return livre, nome, url



def identificador(indice):
    """Identificador fictício determinístico, não pertencente a veículo real."""
    digest = hashlib.sha256(f"vendacerta-demo-{indice}".encode()).hexdigest().upper()
    letras = "ABCDEFGHJKLMNPRSTUVWXYZ"
    placa = "".join(letras[int(digest[i:i+2], 16) % len(letras)] for i in (0, 2, 4))
    placa += str(indice % 10) + letras[indice % len(letras)] + f"{indice % 100:02d}"
    chassi = "9BD" + "".join(letras[int(digest[i:i+2], 16) % len(letras)] for i in range(6, 34, 2))
    return placa, chassi[:17]


def _consulta(sessao, params):
    """Consulta Commons com pausa e repetição moderada para erros temporários."""
    for tentativa in range(3):
        try:
            resposta = sessao.get(API, params={"format": "json", **params}, timeout=40)
            if resposta.status_code in (429, 500, 502, 503, 504):
                if tentativa < 2:
                    time.sleep(3 * (tentativa + 1))
                    continue
            resposta.raise_for_status()
            dados = resposta.json()
            if "error" in dados:
                raise ValueError(str(dados["error"]))
            return dados
        except (requests.Timeout, requests.ConnectionError):
            if tentativa == 2:
                raise
            time.sleep(3 * (tentativa + 1))
    return {}


def _titulo_compativel(titulo, marca, modelo):
    """Exige marca e modelo no nome, aceitando 'VW' para Volkswagen."""
    texto = re.sub(r"[^a-z0-9]+", " ", titulo.lower())
    partes = set(texto.split())
    marca_ok = marca.lower() in partes or (marca == "Volkswagen" and "vw" in partes)
    termos_modelo = re.findall(r"[a-z0-9]+", modelo.lower())
    return marca_ok and all(termo in partes for termo in termos_modelo)


def buscar_imagens(sessao, marca, modelo, quantidade, diagnostico=None):
    """Busca por arquivos e categorias, verificando título, licença e miniatura."""
    diagnostico = diagnostico if diagnostico is not None else {}
    titulos = []
    vistos = set()

    def adicionar(titulo):
        if titulo.startswith("File:") and titulo not in vistos:
            vistos.add(titulo)
            titulos.append(titulo)

    # Busca ampla por arquivos. Evita aspas duplas que reduziam muito os resultados.
    for busca in (f'intitle:"{marca} {modelo}"', f'{marca} {modelo}',
                  f'VW {modelo}' if marca == "Volkswagen" else None):
        if not busca:
            continue
        dados = _consulta(sessao, {
            "action": "query", "list": "search", "srnamespace": 6,
            "srsearch": busca, "srlimit": 50,
        })
        for item in dados.get("query", {}).get("search", []):
            adicionar(item.get("title", ""))
        if len(titulos) >= quantidade * 5:
            break
        time.sleep(0.5)

    # Fallback: categorias cujo nome indica exatamente marca e modelo.
    if len(titulos) < quantidade * 3:
        dados = _consulta(sessao, {
            "action": "query", "list": "search", "srnamespace": 14,
            "srsearch": f'{marca} {modelo}', "srlimit": 20,
        })
        categorias = [x["title"] for x in dados.get("query", {}).get("search", [])
                      if _titulo_compativel(x.get("title", ""), marca, modelo)]
        for categoria in categorias[:4]:
            dados = _consulta(sessao, {
                "action": "query", "list": "categorymembers", "cmtitle": categoria,
                "cmtype": "file", "cmlimit": 50,
            })
            for item in dados.get("query", {}).get("categorymembers", []):
                adicionar(item.get("title", ""))
            time.sleep(0.5)

    diagnostico["candidatas"] = len(titulos)
    compativeis = [t for t in titulos if _titulo_compativel(t, marca, modelo)]
    diagnostico["titulos_compativeis"] = len(compativeis)
    encontrados = []
    for inicio in range(0, len(compativeis), 25):
        lote = compativeis[inicio:inicio + 25]
        dados = _consulta(sessao, {
            "action": "query", "titles": "|".join(lote),
            "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": 1600,
        })
        for pagina in dados.get("query", {}).get("pages", {}).values():
            infos = pagina.get("imageinfo") or []
            if not infos:
                continue
            info = infos[0]
            meta = info.get("extmetadata", {})
            permitida, licenca, url_licenca = licenca_livre(meta)
            diagnostico.setdefault("licencas_encontradas", {})[licenca or "(sem licença)"] = (
                diagnostico.setdefault("licencas_encontradas", {}).get(licenca or "(sem licença)", 0) + 1
            )
            if not permitida:
                continue
            diagnostico["licencas_aceitas"] = diagnostico.get("licencas_aceitas", 0) + 1
            # Algumas respostas da API não incluem thumburl, mesmo com iiurlwidth.
            # Nesses casos, usar a URL original, sem descartar a licença válida.
            url = info.get("thumburl") or info.get("url") or ""
            if url.startswith("//"):
                url = "https:" + url
            if not url.startswith("https://upload.wikimedia.org/"):
                # A API pode omitir url/thumburl; o Commons fornece um
                # redirecionamento oficial a partir do título do arquivo.
                # A resposta final é validada em baixar_foto().
                diagnostico["urls_ausentes"] = diagnostico.get("urls_ausentes", 0) + 1
                titulo_arquivo = pagina.get("title", "")
                if not titulo_arquivo.startswith("File:"):
                    continue
                url = ("https://commons.wikimedia.org/wiki/Special:Redirect/file/"
                       + quote(titulo_arquivo[5:].replace(" ", "_"), safe=""))
                diagnostico["redirecionamentos"] = diagnostico.get("redirecionamentos", 0) + 1
            if not info.get("descriptionurl"):
                diagnostico["paginas_ausentes"] = diagnostico.get("paginas_ausentes", 0) + 1
                continue
            encontrados.append({
                "url": url, "pagina": info["descriptionurl"],
                "titulo": pagina.get("title", ""), "licenca": licenca,
                "url_licenca": url_licenca,
                "autor": re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", ""))[:200],
            })
            if len(encontrados) >= quantidade:
                break
        if len(encontrados) >= quantidade:
            break
        time.sleep(0.5)
    diagnostico["licenciadas"] = len(encontrados)
    return encontrados


# Resolução suficiente para o catálogo web; não baixar originais gigantes.
LARGURA_FOTO = 1600
MAX_DOWNLOAD = 25_000_000  # 25 MB de transferência por tentativa
MAX_PIXELS = 50_000_000  # proteção contra imagens que explodem em memória


def _url_reduzida(item):
    """Solicita thumbnail via redirecionamento oficial do Commons."""
    titulo = item.get("titulo", "")
    if not titulo.startswith("File:"):
        raise ValueError("Título de arquivo ausente")
    caminho = quote(titulo[5:].replace(" ", "_"), safe="")
    return ("https://commons.wikimedia.org/wiki/Special:Redirect/file/"
            + caminho + "?" + urlencode({"width": LARGURA_FOTO}))


def baixar_foto(item):
    """Baixa miniatura em sessão independente (segura para threads)."""
    with requests.Session() as sessao:
        sessao.headers.update(HEADERS)
        # A URL da API frequentemente vem vazia; redirecionamento com width
        # solicita uma miniatura sem transferir a fotografia original.
        with sessao.get(_url_reduzida(item), timeout=(15, 65), stream=True) as resposta:
            resposta.raise_for_status()
            destino = urlparse(resposta.url)
            if destino.scheme != "https" or destino.hostname not in {"upload.wikimedia.org", "thumb.wikimedia.org"}:
                raise ValueError(f"Destino inesperado: {destino.hostname}")
            tamanho = int(resposta.headers.get("Content-Length", "0") or "0")
            if tamanho > MAX_DOWNLOAD:
                raise ValueError("Miniatura maior que 25 MB")
            conteudo = bytearray()
            for bloco in resposta.iter_content(chunk_size=65536):
                conteudo.extend(bloco)
                if len(conteudo) > MAX_DOWNLOAD:
                    raise ValueError("Miniatura maior que 25 MB")
    with Image.open(io.BytesIO(conteudo)) as imagem:
        if imagem.width * imagem.height > MAX_PIXELS:
            raise ValueError("Imagem com pixels demais")
        imagem.load()
        imagem = ImageOps.exif_transpose(imagem)
        if min(imagem.size) < 250:
            raise ValueError("Imagem com resolução insuficiente")
        imagem.thumbnail((LARGURA_FOTO, LARGURA_FOTO), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        imagem.convert("RGB").save(buffer, format="JPEG", quality=82, optimize=True)
        return buffer.getvalue()


def baixar_fotos_paralelo(itens, paginas_usadas, faltam, stderr):
    """Até 3 downloads simultâneos; para assim que atingir o total necessário."""
    validas = []
    vistos = set(paginas_usadas)
    candidatos = []
    for item in itens:
        pagina = item.get("pagina")
        if pagina and pagina not in vistos:
            candidatos.append(item)
            vistos.add(pagina)
    with ThreadPoolExecutor(max_workers=3) as executor:
        for inicio in range(0, len(candidatos), 3):
            lote = candidatos[inicio:inicio + min(3, faltam - len(validas))]
            if not lote:
                break
            futuros = [executor.submit(baixar_foto, item) for item in lote]
            for item, futuro in zip(lote, futuros):
                try:
                    validas.append((item, futuro.result()))
                except (requests.RequestException, ValueError, OSError,
                        UnidentifiedImageError, Image.DecompressionBombError) as exc:
                    stderr.write(f"  Foto descartada: {exc}")
            if len(validas) >= faltam:
                break
            time.sleep(0.5)
    return validas


class Command(BaseCommand):
    help = "Cria veículos fictícios de demonstração, obrigatoriamente com fotos licenciadas."

    def add_arguments(self, parser):
        parser.add_argument("--limite", type=int, default=3, help="Quantidade de modelos a processar; 0 = todos os modelos restantes")
        parser.add_argument("--inicio", type=int, default=1, help="Índice inicial do catálogo (começa em 1)")
        parser.add_argument("--fotos", type=int, default=2, help="Total desejado de fotos por veículo (1 a 20)")
        parser.add_argument("--usuario", help="Username de gerente ativo; opcional se houver um único")
        parser.add_argument("--confirmar", action="store_true", help="Permite mais de três veículos")

    def handle(self, *args, **opts):
        nome = connection.settings_dict.get("NAME")
        if connection.vendor != "postgresql" or nome != "revendacerta_demo":
            raise CommandError("Operação recusada: somente PostgreSQL revendacerta_demo.")
        # Confirma o nome no servidor, não apenas no arquivo settings.py.
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            if cursor.fetchone()[0] != "revendacerta_demo":
                raise CommandError("Banco conectado não é revendacerta_demo.")
        limite, fotos = opts["limite"], opts["fotos"]
        inicio = opts["inicio"]
        if inicio < 1 or inicio > len(CATALOGO) or limite < 0 or not 1 <= fotos <= 20:
            raise CommandError(f"Use --inicio de 1 a {len(CATALOGO)}, --limite >= 0 e --fotos de 1 a 20.")
        fim = len(CATALOGO) if limite == 0 else min(len(CATALOGO), inicio + limite - 1)
        quantidade = fim - inicio + 1
        if quantidade > 3 and not opts["confirmar"]:
            raise CommandError("Para mais de 3 veículos, informe --confirmar.")
        gerentes = Usuario.objects.filter(perfil=Usuario.Perfil.GERENTE, ativo=True)
        if opts["usuario"]:
            gerentes = gerentes.filter(username=opts["usuario"])
        if not gerentes.exists():
            raise CommandError("Não há gerente ativo para atribuir os cadastros.")
        gerente = gerentes.order_by("pk").first()
        sessao = requests.Session()
        sessao.headers.update(HEADERS)
        imagens_por_modelo = {}
        relatorio = []
        criados = 0
        adicionadas = 0
        destino = Path(settings.MEDIA_ROOT) / "creditos_fotos_demo.json"
        try:
            anteriores = json.loads(destino.read_text(encoding="utf-8")) if destino.exists() else []
            if not isinstance(anteriores, list):
                raise ValueError("Formato de créditos inválido")
        except (ValueError, OSError) as exc:
            raise CommandError(f"Não foi possível ler os créditos existentes: {exc}")
        fontes_conhecidas = {(str(x.get("placa")), str(x.get("pagina"))) for x in anteriores if isinstance(x, dict)}
        def salvar_creditos_pendentes():
            if not relatorio:
                return
            destino.parent.mkdir(parents=True, exist_ok=True)
            chaves_atuais = {(x.get("placa"), x.get("pagina")) for x in anteriores}
            anteriores.extend(x for x in relatorio if (x["placa"], x["pagina"]) not in chaves_atuais)
            temporario = destino.with_suffix(".json.tmp")
            temporario.write_text(json.dumps(anteriores, indent=2, ensure_ascii=False), encoding="utf-8")
            temporario.replace(destino)
            fontes_conhecidas.update((x["placa"], x["pagina"]) for x in relatorio)
            relatorio.clear()
        for indice in range(inicio, fim + 1):
            marca, modelo, tipo, preco_base = CATALOGO[indice - 1]
            placa, chassi = identificador(indice)
            existente = Veiculo.objects.filter(chassi=chassi).first()
            atuais = existente.fotos.count() if existente else 0
            faltam = max(0, fotos - atuais)
            if existente and not faltam:
                self.stdout.write(f"[{indice}/{len(CATALOGO)}] Completo: {existente} — {atuais} foto(s)")
                continue
            # Não repetir arquivos já creditados para esta placa.
            paginas_usadas = {pagina for placa_anterior, pagina in fontes_conhecidas if placa_anterior == placa}
            chave = (marca, modelo)
            try:
                diagnostico = {}
                itens = buscar_imagens(sessao, marca, modelo, max(faltam * 8, 80), diagnostico)
                self.stdout.write(
                    f"  Commons: {diagnostico.get('candidatas', 0)} candidatas, "
                    f"{diagnostico.get('titulos_compativeis', 0)} títulos compatíveis, "
                    f"{diagnostico.get('licenciadas', 0)} imagens licenciadas; "
                    f"licenças aceitas: {diagnostico.get('licencas_aceitas', 0)}, "
                    f"URLs ausentes: {diagnostico.get('urls_ausentes', 0)}, "
                    f"URLs recuperadas: {diagnostico.get('redirecionamentos', 0)}"
                )
                validas = baixar_fotos_paralelo(itens, paginas_usadas, faltam, self.stderr)
            except (requests.RequestException, ValueError) as exc:
                self.stderr.write(f"  Erro de busca {marca} {modelo}: {exc}")
                validas = []
            time.sleep(1.2)
            if not validas:
                self.stderr.write(f"[{indice}/{len(CATALOGO)}] PULADO: {marca} {modelo} sem fotos novas válidas")
                continue
            if existente:
                # Acrescenta fotos sem alterar as anteriores ou a foto principal.
                proxima_ordem = max((f.ordem for f in existente.fotos.all()), default=-1) + 1
                with transaction.atomic():
                    for pos, (item, conteudo) in enumerate(validas):
                        foto = FotoVeiculo(veiculo=existente, ordem=proxima_ordem + pos, principal=False)
                        foto.imagem.save(f"demo_{indice:03d}_extra_{proxima_ordem + pos + 1}.jpg", ContentFile(conteudo), save=False)
                        foto.save()
                        relatorio.append({"placa": placa, "modelo": f"{marca} {modelo}", **item})
                salvar_creditos_pendentes()
                adicionadas += len(validas)
                self.stdout.write(self.style.SUCCESS(f"[{indice}/{len(CATALOGO)}] ATUALIZADO: {marca} {modelo} — +{len(validas)} foto(s), total {atuais + len(validas)}"))
                continue
            rng = random.Random(indice + 2211)
            ano = rng.randint(2017, 2024)
            preco = Decimal(str(round(preco_base * rng.uniform(0.85, 1.15), 2)))
            custo = (preco * Decimal("0.82")).quantize(Decimal("0.01"))
            origem = Veiculo.Origem.COMPRADO
            with transaction.atomic():
                veiculo = Veiculo(
                    placa=placa, chassi=chassi, renavam=f"{indice:011d}",
                    marca=marca, modelo=modelo, ano_fabricacao=ano,
                    ano_modelo=ano + rng.choice([0, 1]),
                    cor=rng.choice(["Prata", "Preto", "Branco", "Cinza", "Azul"]),
                    combustivel="Flex", tipo=tipo,
                    cambio=rng.choice([Veiculo.Cambio.MANUAL, Veiculo.Cambio.AUTOMATICO]),
                    quilometragem=max(1000, (2026 - ano) * rng.randint(7000, 13000)),
                    opcionais="Ar-condicionado, direção assistida, vidros elétricos",
                    situacao=Veiculo.Situacao.DISPONIVEL,
                    status=Veiculo.Status.DISPONIVEL, origem=origem,
                    custo_aquisicao=custo, preco_venda=preco, criado_por=gerente,
                )
                veiculo.full_clean()
                veiculo.save()
                for pos, (item, conteudo) in enumerate(validas):
                    foto = FotoVeiculo(veiculo=veiculo, ordem=pos, principal=(pos == 0))
                    foto.imagem.save(f"demo_{indice:03d}_{pos+1}.jpg", ContentFile(conteudo), save=False)
                    foto.save()
                    relatorio.append({"placa": placa, "modelo": f"{marca} {modelo}", **item})
                LancamentoFinanceiro.objects.create(
                    veiculo=veiculo, tipo=LancamentoFinanceiro.Tipo.CUSTO_AQUISICAO,
                    valor=custo, descricao="Custo de aquisição — demonstração",
                    registrado_por=gerente,
                )
            salvar_creditos_pendentes()
            criados += 1
            self.stdout.write(self.style.SUCCESS(f"[{indice}/{len(CATALOGO)}] OK: {marca} {modelo} — {len(validas)} foto(s)"))
        self.stdout.write(self.style.SUCCESS(
            f"Concluído: {criados} veículo(s) novos, {adicionadas} foto(s) adicionadas a veículos existentes. "
            f"Catálogo: {len(CATALOGO)} modelos distintos. Créditos: {destino}"
        ))
