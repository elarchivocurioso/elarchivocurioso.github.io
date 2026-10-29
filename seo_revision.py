"""
seo_revision.py - Revisa el SEO de la web ya generada (Web/) y de folio13.com, sin cambiar nada.

Uso:
    python seo_revision.py            revisión local + comprobaciones en línea
    python seo_revision.py --local    solo la revisión local (sin internet)
    python seo_revision.py --json     además, deja el resultado en Posicionamiento/seo_revision.json

Comprueba:
  - Cada página: <title> (único, 20-110 caracteres), meta description (50-160), canonical, un solo <h1>,
    imágenes con alt, JSON-LD que se pueda leer y enlaces internos que lleven a un archivo que exista.
  - sitemap.xml: cada URL tiene su página.
  - Folios cuyo título para buscadores no nombra el caso (sin "titulo_seo" ni "titulo_articulo").
  - En línea: portada, sitemap, robots, ads.txt, archivo de Google y meta de Bing responden bien, y los vídeos de
    YouTube de los folios siguen siendo públicos (si uno pasa a privado, la página enseña un vídeo roto).
Sale con código 1 si hay errores (no avisos).
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

WEB = Path(__file__).resolve().parent
BASE = WEB.parent
DATOS = WEB / "datos" / "expedientes.json"
SALIDA_JSON = BASE / "Posicionamiento" / "seo_revision.json"
VERIFICACION_GOOGLE = "googlefc2f29286514b152.html"
IGNORAR = {"404.html", VERIFICACION_GOOGLE}


class Pagina(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title, self.en_title, self.desc, self.canonical = "", False, None, None
        self.h1, self.img_sin_alt, self.enlaces, self.jsonld = 0, 0, [], []
        self._ld, self._ld_txt = False, ""
        self.fuera_head = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title" and not self.fuera_head:   # los <title> de los SVG (mapa) no cuentan
            self.en_title = True
        elif tag == "meta" and a.get("name") == "description":
            self.desc = a.get("content") or ""
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        elif tag == "h1":
            self.h1 += 1
        elif tag == "img" and not (a.get("alt") or "").strip() and a.get("aria-hidden") != "true":
            self.img_sin_alt += 1
        elif tag == "a" and a.get("href"):
            self.enlaces.append(a["href"])
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._ld, self._ld_txt = True, ""

    def handle_endtag(self, tag):
        if tag == "title":
            self.en_title = False
        elif tag == "head":
            self.fuera_head = True
        elif tag == "script" and self._ld:
            self._ld = False
            self.jsonld.append(self._ld_txt)

    def handle_data(self, data):
        if self.en_title:
            self.title += data
        if self._ld:
            self._ld_txt += data


def dominio() -> str:
    canal = json.loads(DATOS.read_text(encoding="utf-8-sig"))["canal"]
    return canal.get("dominio") or "elarchivocurioso.github.io"


def revisar_local(errores: list[str], avisos: list[str]) -> int:
    url = f"https://{dominio()}"
    titulos: dict[str, list[str]] = {}
    paginas = [p for p in WEB.rglob("*.html")
               if not any(x in p.parts for x in ("datos", "marca", "promo", "og", "miniaturas", ".git"))
               and p.name not in IGNORAR]
    for p in paginas:
        ruta = p.relative_to(WEB).as_posix()
        h = Pagina()
        h.feed(p.read_text(encoding="utf-8", errors="replace"))
        t = re.sub(r"\s+", " ", h.title).strip()
        titulos.setdefault(t, []).append(ruta)
        if not t:
            errores.append(f"{ruta}: sin <title>")
        elif not 20 <= len(t) <= 110:
            avisos.append(f"{ruta}: <title> de {len(t)} caracteres")
        if h.desc is None:
            errores.append(f"{ruta}: sin meta description")
        elif not 50 <= len(h.desc) <= 160:
            avisos.append(f"{ruta}: meta description de {len(h.desc)} caracteres")
        if not h.canonical:
            errores.append(f"{ruta}: sin canonical")
        elif not h.canonical.startswith(url):
            errores.append(f"{ruta}: canonical con otro dominio ({h.canonical})")
        if h.h1 != 1:
            (errores if h.h1 == 0 else avisos).append(f"{ruta}: {h.h1} <h1>")
        if h.img_sin_alt:
            avisos.append(f"{ruta}: {h.img_sin_alt} imagen(es) sin alt")
        for bloque in h.jsonld:
            try:
                json.loads(bloque)
            except ValueError:
                errores.append(f"{ruta}: JSON-LD que no se puede leer")
        for href in h.enlaces:
            u = urlparse(href)
            if u.scheme in ("mailto", "tel", "javascript") or href.startswith("#"):
                continue
            if u.netloc and u.netloc.replace("www.", "") != dominio():
                continue
            camino = unquote(u.path)
            if u.netloc:
                destino = WEB / camino.lstrip("/")
            else:
                destino = (p.parent / camino).resolve()
            if camino.endswith("/") or destino.is_dir():
                destino = destino / "index.html"
            if camino and not destino.exists():
                errores.append(f"{ruta}: enlace roto → {href}")
    for t, rutas in titulos.items():
        if t and len(rutas) > 1:
            avisos.append(f"Título repetido en {len(rutas)} páginas: «{t[:70]}» ({', '.join(rutas[:3])})")
    # sitemap: cada URL con su archivo
    mapa = WEB / "sitemap.xml"
    if not mapa.exists():
        errores.append("No hay sitemap.xml")
    else:
        for loc in re.findall(r"<loc>([^<]+)</loc>", mapa.read_text(encoding="utf-8")):
            camino = unquote(urlparse(loc).path).lstrip("/")
            destino = WEB / (camino + "index.html" if camino.endswith("/") or not camino else camino)
            if not destino.exists():
                errores.append(f"sitemap.xml: {loc} no tiene página")
    # Folios cuyo título para buscadores sale del de YouTube (puede no nombrar el caso)
    for e in json.loads(DATOS.read_text(encoding="utf-8-sig"))["expedientes"]:
        if not e.get("titulo_seo") and not e.get("titulo_articulo"):
            avisos.append(f"Título SEO: {e.get('num', '?')} usa el de YouTube («{e['titulo'][:60]}»); "
                          "revisar si nombra el caso o ponerle \"titulo_seo\"")
    return len(paginas)


def pedir(url: str) -> tuple[int, str]:
    peticion = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Folio13 revision SEO)"})
    try:
        with urllib.request.urlopen(peticion, timeout=20) as r:
            return r.status, r.read(400_000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as ex:
        return ex.code, ""
    except Exception as ex:   # sin red, DNS, tiempo agotado
        return 0, str(ex)


def revisar_en_linea(errores: list[str], avisos: list[str]) -> None:
    url = f"https://{dominio()}"
    for camino, debe in (("/", "<title>"), ("/sitemap.xml", "<urlset"), ("/robots.txt", "Sitemap:"),
                         ("/ads.txt", "pub-"), (f"/{VERIFICACION_GOOGLE}", "google-site-verification"),
                         ("/llms.txt", "#")):
        codigo, texto = pedir(url + camino)
        if codigo != 200 or debe not in texto:
            errores.append(f"En línea: {url}{camino} responde {codigo or texto[:60]}")
    codigo, texto = pedir(url + "/")
    if codigo == 200 and 'name="msvalidate.01"' not in texto:
        errores.append("En línea: la portada ha perdido la meta de Bing (msvalidate.01)")
    # Vídeos de YouTube: oEmbed responde 200 solo si el vídeo es público (o no listado)
    for e in json.loads(DATOS.read_text(encoding="utf-8-sig"))["expedientes"]:
        if not e.get("youtube"):
            continue
        codigo, _ = pedir(f"https://www.youtube.com/oembed?format=json&url=https://www.youtube.com/watch?v={e['youtube']}")
        if codigo in (401, 403, 404):
            errores.append(f"Vídeo no público en la web: {e.get('num', '?')} ({e['youtube']}) «{e['titulo'][:50]}»")
        elif codigo != 200:
            avisos.append(f"No se pudo comprobar el vídeo de {e.get('num', '?')} ({codigo})")


def main() -> None:
    errores: list[str] = []
    avisos: list[str] = []
    n = revisar_local(errores, avisos)
    if "--local" not in sys.argv:
        revisar_en_linea(errores, avisos)
    print(f"Revisión SEO: {n} páginas · {len(errores)} error(es) · {len(avisos)} aviso(s)")
    for x in errores:
        print("  ERROR", x)
    for x in avisos:
        print("  aviso", x)
    if "--json" in sys.argv:
        SALIDA_JSON.write_text(json.dumps({"paginas": n, "errores": errores, "avisos": avisos},
                                          ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.exit(1 if errores else 0)


if __name__ == "__main__":
    main()
