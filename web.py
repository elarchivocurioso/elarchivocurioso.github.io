"""
web.py - Genera y publica la web de El Archivo Curioso (elarchivocurioso.github.io).

Uso:
    python web.py generar     Rehace la web a partir de datos/expedientes.json
    python web.py publicar    Genera la web y la sube a GitHub (git commit + push)

Para añadir un vídeo o Short, añade una entrada a datos/expedientes.json:
    {
      "youtube": "ID del vídeo",
      "tipo": "video" | "short",
      "titulo": "...",
      "fecha": "AAAA-MM-DDTHH:MM",      fecha (y hora local, opcional) de publicación en YouTube
      "miniatura": "Identidad/Miniaturas/miniatura-A001-baile-1518.png",   opcional, ruta desde "Canal YouTube"
      "epoca": "1518",                  opcional
      "lugar": "Estrasburgo",           opcional
      "resumen": "2-3 frases",
      "curiosidades": ["...", "..."],
      "fuentes": [{"titulo": "...", "url": "https://..."}],
      "etiquetas": ["..."]              opcional
    }
Las entradas con fecha futura no se muestran hasta esa fecha y hora (vídeos programados);
aparecen la siguiente vez que se ejecute "publicar".
Un expediente que ya está en redes pero aún no en YouTube lleva "youtube": "" y "num": "A002": su página
muestra la miniatura en lugar del reproductor. Cuando la sincronización añade su entrada de YouTube (mismo
título), se usa esa y hereda el artículo y las lecturas de la provisional.
Solo usa la biblioteca estándar de Python.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, datetime
from email.utils import format_datetime
from html import escape
from pathlib import Path
from xml.sax.saxutils import escape as escape_xml

WEB = Path(__file__).resolve().parent
DATOS = WEB / "datos" / "expedientes.json"
CLAVE_INDEXNOW = WEB / "datos" / "indexnow.txt"
LOGO_ORIGEN = WEB.parent / "Identidad" / "Archivo Curioso" / "foto-perfil.png"
BANNER_ORIGEN = WEB.parent / "Identidad" / "Archivo Curioso" / "banner.png"
URL = "https://elarchivocurioso.github.io"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=Special+Elite&family=Lora:ital,wght@0,500;0,700;1,500&display=swap');
:root { --tinta:#1A1410; --tinta-2:#2A211A; --tinta-3:#362B22; --pergamino:#EBDDBF; --pergamino-2:#C9B48A;
        --sepia:#6B4F35; --lacre:#9E2B25; --lacre-claro:#C2443B; --oro:#C8A04A; }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Lora',Georgia,serif; color:var(--pergamino); line-height:1.6; min-height:100vh;
  background: radial-gradient(ellipse 80% 50% at 50% 0%, rgba(200,160,74,.12), transparent 70%),
              repeating-linear-gradient(0deg, rgba(255,255,255,.012) 0 2px, transparent 2px 6px), var(--tinta); }
a { color:var(--oro); }
.ancho { max-width:1100px; margin:0 auto; padding:0 16px; }
.etiqueta { font-family:'Special Elite','Courier New',monospace; letter-spacing:.16em; color:var(--oro); font-size:14px; text-transform:uppercase; }

/* Sello de lacre */
.sello { --t:64px; position:relative; flex:none; width:var(--t); height:var(--t); border-radius:50%;
  background: radial-gradient(circle at 35% 30%, rgba(255,255,255,.25), transparent 35%),
              radial-gradient(circle at 50% 50%, var(--lacre-claro) 0 55%, var(--lacre) 75%, #6E1C18 100%);
  box-shadow:0 0 0 calc(var(--t)*.035) #7C211C, 0 calc(var(--t)*.06) calc(var(--t)*.12) rgba(0,0,0,.55);
  display:flex; align-items:center; justify-content:center; text-decoration:none; }
.sello::after { content:""; position:absolute; inset:calc(var(--t)*.1); border-radius:50%; border:calc(var(--t)*.025) solid rgba(60,10,8,.45); }
.sello span { font-family:'Playfair Display',Georgia,serif; font-weight:900; font-style:italic; font-size:calc(var(--t)*.4); color:#F3D9C2; letter-spacing:-.04em; }

/* Cabecera */
header { border-bottom:1px solid rgba(201,180,138,.15); }
header .ancho { display:flex; align-items:center; gap:14px; padding-top:18px; padding-bottom:18px; }
header .nombre { font-family:'Playfair Display',Georgia,serif; font-weight:900; font-size:24px; color:var(--pergamino); text-decoration:none; line-height:1.1; }
header .nombre em { color:var(--lacre-claro); }
header nav { margin-left:auto; display:flex; gap:18px; flex-wrap:wrap; }
header nav a { color:var(--pergamino-2); text-decoration:none; font-weight:700; font-size:15px; }
header nav a:hover { color:var(--oro); }

/* Portada */
.portada { text-align:center; padding:72px 0 40px; display:flex; flex-direction:column; align-items:center; gap:18px; }
.portada .sello { --t:120px; }
.portada h1 { font-family:'Playfair Display',Georgia,serif; font-weight:900; font-size:clamp(40px,8vw,76px); line-height:1; }
.portada h1 em { color:var(--lacre-claro); }
.portada .lema { font-style:italic; font-size:clamp(18px,3vw,24px); color:rgba(235,221,191,.85); }
.portada p.desc { max-width:640px; color:var(--pergamino-2); font-size:17px; }
.boton { display:inline-block; padding:12px 26px; border-radius:6px; background:var(--lacre); color:#F3D9C2;
  font-family:'Special Elite','Courier New',monospace; letter-spacing:.08em; text-decoration:none; font-size:16px;
  box-shadow:0 0 0 1px #7C211C, 0 8px 20px rgba(0,0,0,.4); }
.boton:hover { background:var(--lacre-claro); }

/* Filtros y fichas */
.filtros { display:flex; gap:10px; justify-content:center; margin:8px 0 28px; flex-wrap:wrap; }
.filtros button { font-family:'Special Elite','Courier New',monospace; letter-spacing:.08em; font-size:14px; cursor:pointer;
  padding:8px 16px; border-radius:4px; border:1px solid rgba(201,180,138,.35); background:transparent; color:var(--pergamino-2); }
.filtros button.activo { background:var(--pergamino); color:var(--tinta); border-color:var(--pergamino); }
.rejilla { display:grid; grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); gap:22px; padding-bottom:64px; }
.ficha { display:flex; flex-direction:column; background:var(--tinta-2); border:1px solid rgba(201,180,138,.18); border-radius:8px;
  overflow:hidden; text-decoration:none; color:inherit; transition:transform .15s, border-color .15s; }
.ficha:hover { transform:translateY(-3px); border-color:var(--oro); }
.ficha .img { position:relative; aspect-ratio:16/9; background:var(--tinta-3) center/cover no-repeat; }
.ficha .tipo { position:absolute; right:10px; top:10px; padding:3px 9px; border-radius:3px; font-family:'Special Elite',monospace;
  font-size:12px; letter-spacing:.1em; background:var(--lacre); color:#F3D9C2; }
.ficha .tipo.short { background:var(--oro); color:var(--tinta); }
.ficha .txt { padding:14px 16px 18px; display:flex; flex-direction:column; gap:6px; }
.ficha h3 { font-family:'Playfair Display',Georgia,serif; font-size:19px; line-height:1.25; color:var(--pergamino); }
.ficha .meta { font-size:13px; color:var(--pergamino-2); }
.vacio { text-align:center; padding:40px 16px 80px; color:var(--pergamino-2); }
.vacio .sello { --t:72px; margin:0 auto 18px; opacity:.85; }

/* Página de expediente */
.expediente { padding:40px 0 72px; }
.volver { text-decoration:none; font-weight:700; font-size:15px; }
.expediente h1 { font-family:'Playfair Display',Georgia,serif; font-weight:900; font-size:clamp(30px,5.5vw,48px); line-height:1.1; margin:16px 0 14px; }
.datos { display:flex; flex-wrap:wrap; gap:8px 22px; margin-bottom:26px; font-family:'Special Elite',monospace; font-size:14px; color:var(--pergamino-2); letter-spacing:.04em; }
.datos b { color:var(--oro); font-weight:400; }
.reproductor { position:relative; width:100%; aspect-ratio:16/9; border-radius:8px; overflow:hidden; background:#000; box-shadow:0 20px 50px rgba(0,0,0,.5); }
.reproductor.short { max-width:360px; aspect-ratio:9/16; margin:0 auto; }
.reproductor iframe { position:absolute; inset:0; width:100%; height:100%; border:0; }
.bloque { margin-top:36px; }
.bloque h2 { font-family:'Playfair Display',Georgia,serif; font-size:26px; margin-bottom:12px; color:var(--pergamino); }
.bloque p { font-size:18px; }
.curiosidades { list-style:none; display:flex; flex-direction:column; gap:12px; }
.curiosidades li { position:relative; padding:14px 16px 14px 52px; background:var(--tinta-2); border-left:3px solid var(--lacre); border-radius:4px; font-size:17px; }
.curiosidades li::before { content:counter(c); counter-increment:c; position:absolute; left:14px; top:12px; font-family:'Playfair Display',serif; font-weight:900; font-size:22px; color:var(--oro); }
.curiosidades { counter-reset:c; }
.fuentes li { margin:6px 0 6px 20px; }
.etiquetas { display:flex; flex-wrap:wrap; gap:8px; }
.etiquetas span { font-family:'Special Elite',monospace; font-size:13px; padding:4px 10px; border:1px solid rgba(201,180,138,.3); border-radius:3px; color:var(--pergamino-2); }
.navegacion { display:flex; justify-content:space-between; gap:16px; margin-top:48px; flex-wrap:wrap; }
.navegacion a { text-decoration:none; font-weight:700; max-width:48%; }

/* Texto legal */
.legal { padding:40px 0 72px; max-width:760px; }
.legal h1 { font-family:'Playfair Display',Georgia,serif; font-size:clamp(30px,6vw,44px); margin:16px 0 6px; }
.legal .fecha { font-size:14px; color:var(--pergamino-2); margin-bottom:24px; }
.legal h2 { color:var(--oro); font-family:'Playfair Display',Georgia,serif; font-size:21px; margin:28px 0 8px; }
.legal p, .legal li { font-size:16px; }
.legal ul { padding-left:22px; }

.articulo p { margin-bottom:14px; }
.relacionado { padding:14px 16px; border-left:3px solid var(--oro); background:var(--tinta-2); border-radius:4px; }
.relacionado p { font-size:17px; }
.compartir { margin-top:40px; padding:20px 16px; border:1px solid rgba(201,180,138,.25); border-radius:8px; background:var(--tinta-2); text-align:center; }
.compartir p { margin-bottom:12px; color:var(--pergamino-2); }
.compartir div { display:flex; flex-wrap:wrap; gap:10px; justify-content:center; }
.compartir a, .compartir button { font-family:'Special Elite','Courier New',monospace; font-size:14px; letter-spacing:.06em; cursor:pointer;
  padding:8px 14px; border-radius:4px; border:1px solid rgba(201,180,138,.35); background:transparent; color:var(--pergamino); text-decoration:none; }
.compartir a:hover, .compartir button:hover { border-color:var(--oro); color:var(--oro); }
.nota { color:var(--pergamino-2); font-size:15px; }
.apoyo { display:flex; align-items:center; gap:22px; flex-wrap:wrap; margin-top:8px; margin-bottom:48px; padding:24px 16px;
  border:1px solid rgba(201,180,138,.25); border-radius:8px; background:var(--tinta-2); }
.apoyo div:nth-child(2) { flex:1; min-width:220px; }
.apoyo h2 { font-family:'Playfair Display',Georgia,serif; font-size:22px; }
.apoyo p { color:var(--pergamino-2); font-size:16px; }
footer small { display:inline-block; margin-top:6px; font-size:12px; }
footer { border-top:1px solid rgba(201,180,138,.15); padding:24px 16px; text-align:center; font-size:14px; color:rgba(235,221,191,.6); }
footer a { color:rgba(235,221,191,.8); }
@media (max-width:600px) { header nav { display:none; } }
"""

FILTRO_JS = """
<script>
document.querySelectorAll('.filtros button').forEach(function (b) {
  b.addEventListener('click', function () {
    document.querySelectorAll('.filtros button').forEach(function (x) { x.classList.remove('activo'); });
    b.classList.add('activo');
    var f = b.dataset.filtro;
    document.querySelectorAll('.ficha').forEach(function (c) {
      c.style.display = (f === 'todos' || c.dataset.tipo === f) ? '' : 'none';
    });
  });
});
</script>
"""


def fecha_larga(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t.lower()).strip("-")
    return t[:70].rstrip("-") or "expediente"


def url_absoluta(ruta: str) -> str:
    return ruta if ruta.startswith("http") else f"{URL}/{ruta}"


def fecha_iso(fecha: str) -> str:
    """Fecha local del expediente con zona horaria, como piden los buscadores."""
    return datetime.fromisoformat(fecha).astimezone().isoformat(timespec="seconds")


def pagina(titulo: str, cuerpo: str, canal: dict, raiz: str = "", descripcion: str = "", extra: str = "",
           ruta: str = "", imagen: str = "compartir.png", tipo_og: str = "website", jsonld=None) -> str:
    desc = escape(descripcion or canal["lema"])
    # Etiquetas para buscadores (Google, Bing) y para las vistas previas al compartir en redes
    seo = (f'<link rel="canonical" href="{URL}/{ruta}">\n'
           f'<meta property="og:site_name" content="{escape(canal["nombre"])}">\n'
           '<meta property="og:locale" content="es_ES">\n'
           f'<meta property="og:type" content="{tipo_og}">\n'
           f'<meta property="og:title" content="{escape(titulo)}">\n'
           f'<meta property="og:description" content="{desc}">\n'
           f'<meta property="og:url" content="{URL}/{ruta}">\n'
           f'<meta property="og:image" content="{escape(url_absoluta(imagen))}">\n'
           '<meta name="twitter:card" content="summary_large_image">\n'
           # Imágenes grandes en Google Discover y en los resultados
           '<meta name="robots" content="max-image-preview:large">\n'
           f'<link rel="alternate" type="application/rss+xml" title="{escape(canal["nombre"])}" href="{URL}/feed.xml">\n')
    if canal.get("google_verificacion"):
        seo += f'<meta name="google-site-verification" content="{escape(canal["google_verificacion"])}">\n'
    if canal.get("bing_verificacion"):
        seo += f'<meta name="msvalidate.01" content="{escape(canal["bing_verificacion"])}">\n'
    if jsonld:
        seo += ('<script type="application/ld+json">'
                + json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/") + "</script>\n")
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titulo)}</title>
<meta name="description" content="{desc}">
{seo}<link rel="icon" href="{raiz}logo.png">
<style>{CSS}</style>
</head>
<body>
<header><div class="ancho">
  <a class="sello" style="--t:46px" href="{raiz}index.html" aria-label="Inicio"><span>AC</span></a>
  <a class="nombre" href="{raiz}index.html">El Archivo <em>Curioso</em></a>
  <nav><a href="{raiz}index.html#expedientes">Expedientes</a><a href="{raiz}acerca.html">El archivo</a><a href="{escape(canal['youtube'])}">YouTube</a></nav>
</div></header>
{cuerpo}
{suscripcion(canal)}
{apoyo(canal)}
<footer>© {date.today().year} {escape(canal['nombre'])} · <a href="{raiz}acerca.html">Acerca del archivo</a> · <a href="{raiz}privacidad.html">Política de privacidad</a> · <a href="{URL}/feed.xml">RSS</a>{aviso_afiliados(canal)}</footer>
{extra}
</body>
</html>
"""


def apoyo(canal: dict) -> str:
    """Bloque de donaciones; no aparece hasta que haya un enlace en "donaciones_url"."""
    if not canal.get("donaciones_url"):
        return ""
    return (f'<section class="apoyo ancho"><div class="sello" style="--t:54px"><span>AC</span></div>'
            f'<div><h2>¿Te gusta El Archivo Curioso?</h2><p>Cada expediente lleva horas de investigación. '
            f'Si quieres ayudar a abrir el siguiente, puedes invitarnos a un café.</p></div>'
            f'<a class="boton" href="{escape(canal["donaciones_url"])}" rel="noopener">'
            f'{escape(canal.get("donaciones_texto") or "INVÍTANOS A UN CAFÉ")}</a></section>')


def suscripcion(canal: dict) -> str:
    """Invitación a la newsletter; no aparece hasta que haya un enlace en "newsletter_url"."""
    if not canal.get("newsletter_url"):
        return ""
    return (f'<section class="apoyo ancho"><div class="sello" style="--t:54px"><span>AC</span></div>'
            f'<div><h2>Un expediente a la semana, en tu correo</h2><p>Historias reales que parecen inventadas, '
            f'con fuentes. Gratis y sin spam: te das de baja con un clic.</p></div>'
            f'<a class="boton" href="{escape(canal["newsletter_url"])}" rel="noopener">SUSCRIBIRME</a></section>')


def aviso_afiliados(canal: dict) -> str:
    # Texto obligatorio del programa de Afiliados de Amazon
    if not canal.get("amazon_tag"):
        return ""
    return ("<br><small>En calidad de Afiliado de Amazon, obtenemos ingresos por las compras adscritas "
            "que cumplen los requisitos aplicables.</small>")


def enlace_libro(libro: dict, canal: dict) -> str:
    texto = f"<i>{escape(libro['titulo'])}</i>" + (f", {escape(libro['autor'])}" if libro.get("autor") else "")
    if libro.get("nota"):
        texto += f" <span class='nota'>— {escape(libro['nota'])}</span>"
    if not canal.get("amazon_tag"):
        return f"<li>{texto}</li>"
    busqueda = urllib.parse.quote_plus(f"{libro['titulo']} {libro.get('autor', '')}".strip())
    url = f"https://www.amazon.es/s?k={busqueda}&tag={urllib.parse.quote(canal['amazon_tag'])}"
    return f'<li><a href="{escape(url)}" rel="sponsored noopener">{texto}</a></li>'


COPIAR_JS = """
<script>
document.querySelectorAll('.copiar').forEach(function (b) {
  b.addEventListener('click', function () {
    navigator.clipboard.writeText(b.dataset.url).then(function () { b.textContent = '¡ENLACE COPIADO!'; });
  });
});
</script>
"""


def compartir(e: dict, ruta: str) -> str:
    """Botones para compartir el expediente (enlaces normales, sin scripts de terceros)."""
    url = f"{URL}/{ruta}"
    texto = f"{e['titulo']} · El Archivo Curioso"
    q = urllib.parse.quote
    redes = (("WHATSAPP", f"https://wa.me/?text={q(texto + ' ' + url)}"),
             ("TELEGRAM", f"https://t.me/share/url?url={q(url)}&text={q(texto)}"),
             ("X", f"https://twitter.com/intent/tweet?url={q(url)}&text={q(texto)}"),
             ("MENÉAME", f"https://www.meneame.net/submit?url={q(url)}"),
             ("REDDIT", f"https://www.reddit.com/submit?url={q(url)}&title={q(e['titulo'])}"))
    botones = "".join(f'<a href="{escape(u)}" rel="noopener" target="_blank">{n}</a>' for n, u in redes)
    return (f'<div class="compartir"><p>¿Conoces a alguien a quien le encantaría este expediente? Pásaselo.</p>'
            f'<div>{botones}<button class="copiar" data-url="{escape(url)}">COPIAR ENLACE</button></div></div>')


def ficha(e: dict) -> str:
    tipo = "short" if e.get("tipo") == "short" else "video"
    meta = " · ".join(x for x in (e.get("epoca", ""), e.get("lugar", ""), fecha_larga(e["fecha"])) if x)
    return (f'<a class="ficha" data-tipo="{tipo}" href="expedientes/{e["_slug"]}.html">'
            f'<div class="img" style="background-image:url({escape(e["_img"])})">'
            f'<span class="tipo {tipo}">{"SHORT" if tipo == "short" else "VÍDEO"}</span></div>'
            f'<div class="txt"><h3>{escape(e["titulo"])}</h3><div class="meta">{escape(meta)}</div></div></a>')


def inicio(canal: dict, expedientes: list[dict]) -> str:
    if expedientes:
        lista = ('<div class="filtros"><button class="activo" data-filtro="todos">TODOS</button>'
                 '<button data-filtro="video">VÍDEOS</button><button data-filtro="short">SHORTS</button></div>'
                 f'<div class="rejilla">{"".join(ficha(e) for e in expedientes)}</div>')
    else:
        lista = ('<div class="vacio"><div class="sello"><span>AC</span></div>'
                 '<p>Los primeros expedientes se están catalogando.<br>Muy pronto los encontrarás aquí.</p></div>')
    cuerpo = f"""<main class="ancho">
<section class="portada">
  <div class="sello"><span>AC</span></div>
  <div class="etiqueta">Expedientes de historia y curiosidades</div>
  <h1>El Archivo <em>Curioso</em></h1>
  <div class="lema">{escape(canal['lema'])}</div>
  <p class="desc">{escape(canal['descripcion'])}</p>
  <a class="boton" href="{escape(canal['youtube'])}">VER EL CANAL EN YOUTUBE</a>
</section>
<section id="expedientes">
  <div class="etiqueta" style="text-align:center; margin-bottom:12px">Expedientes abiertos: {len(expedientes)}</div>
  {lista}
</section>
</main>"""
    jsonld = [
        {"@context": "https://schema.org", "@type": "WebSite", "name": canal["nombre"], "url": f"{URL}/",
         "inLanguage": "es", "description": canal["descripcion"]},
        {"@context": "https://schema.org", "@type": "Organization", "name": canal["nombre"], "url": f"{URL}/",
         "logo": f"{URL}/logo.png", "sameAs": [canal["youtube"]]},
    ]
    return pagina(f"{canal['nombre']} | {canal['lema']}", cuerpo, canal, descripcion=canal["descripcion"],
                  extra=FILTRO_JS if expedientes else "", jsonld=jsonld)


def expediente(e: dict, anterior: dict | None, siguiente: dict | None, canal: dict) -> str:
    tipo = "short" if e.get("tipo") == "short" else "video"
    datos = "".join(f"<span><b>{k}:</b> {escape(v)}</span>" for k, v in (
        ("Época", e.get("epoca", "")), ("Lugar", e.get("lugar", "")), ("Publicado", fecha_larga(e["fecha"])),
        ("Formato", "Short" if tipo == "short" else "Vídeo")) if v)
    bloques = f'<div class="bloque"><h2>El caso</h2><p>{escape(e["resumen"])}</p></div>' if e.get("resumen") else ""
    # Artículo completo: lista de secciones {"titulo": "...", "parrafos": ["...", ...]}
    for seccion in e.get("articulo", []):
        titulo = f'<h2>{escape(seccion["titulo"])}</h2>' if seccion.get("titulo") else ""   # la entradilla no lleva título
        bloques += (f'<div class="bloque articulo">{titulo}'
                    + "".join(f"<p>{escape(p)}</p>" for p in seccion["parrafos"]) + "</div>")
    if e.get("curiosidades"):
        bloques += ('<div class="bloque"><h2>Curiosidades del expediente</h2><ul class="curiosidades">'
                    + "".join(f"<li>{escape(c)}</li>" for c in e["curiosidades"]) + "</ul></div>")
    if e.get("lecturas"):
        bloques += ('<div class="bloque"><h2>Para saber más</h2><ul class="fuentes">'
                    + "".join(enlace_libro(l, canal) for l in e["lecturas"]) + "</ul></div>")
    if e.get("fuentes"):
        bloques += ('<div class="bloque"><h2>Fuentes</h2><ul class="fuentes">'
                    + "".join(f'<li><a href="{escape(f["url"])}" rel="noopener">{escape(f["titulo"])}</a></li>'
                              for f in e["fuentes"]) + "</ul></div>")
    if e.get("etiquetas"):
        bloques += ('<div class="bloque etiquetas">'
                    + "".join(f"<span>#{escape(t)}</span>" for t in e["etiquetas"]) + "</div>")
    nav = '<div class="navegacion">'
    nav += f'<a href="{anterior["_slug"]}.html">← {escape(anterior["titulo"])}</a>' if anterior else "<span></span>"
    nav += f'<a href="{siguiente["_slug"]}.html" style="text-align:right">{escape(siguiente["titulo"])} →</a>' if siguiente else ""
    nav += "</div>"
    if e.get("youtube"):
        video = f"""<div class="reproductor {tipo}"><iframe src="https://www.youtube-nocookie.com/embed/{escape(e['youtube'])}"
  title="{escape(e['titulo'])}" loading="lazy" allowfullscreen
  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"></iframe></div>
<p style="margin-top:14px; text-align:center"><a href="https://www.youtube.com/watch?v={escape(e['youtube'])}">Ver en YouTube</a></p>"""
    else:
        # Aún no está en YouTube: miniatura y aviso de dónde verlo
        img = e["_img"] if e["_img"].startswith("http") else "../" + e["_img"]
        video = (f'<img src="{escape(img)}" alt="{escape(e["titulo"])}" style="display:block; width:100%; border-radius:6px">'
                 '<p style="margin-top:14px; text-align:center">El vídeo de este expediente ya está en '
                 '<a href="https://www.tiktok.com/@elarchivocurioso7" rel="noopener">TikTok</a> y muy pronto llegará a '
                 f'<a href="{escape(canal["youtube"])}">YouTube</a>.</p>')
    if e.get("_episodio"):
        ep = e["_episodio"]
        video += (f'<div class="bloque relacionado"><p>📜 Este Short es un adelanto. El expediente completo, con todo el '
                  f'contexto y las fuentes: <a href="{ep["_slug"]}.html">{escape(ep["titulo"])}</a></p></div>')
    if e.get("_shorts"):
        video += ('<div class="bloque relacionado"><p>⚡ En 1 minuto: '
                  + " · ".join(f'<a href="{s["_slug"]}.html">{escape(s["titulo"])}</a>' for s in e["_shorts"])
                  + "</p></div>")
    cuerpo = f"""<main class="ancho expediente">
<a class="volver" href="../index.html#expedientes">← Todos los expedientes</a>
<h1>{escape(e['titulo'])}</h1>
<div class="datos">{datos}</div>
{video}
{bloques}
{compartir(e, f"expedientes/{e['_slug']}.html")}
{nav}
</main>"""
    ruta = f"expedientes/{e['_slug']}.html"
    publisher = {"@type": "Organization", "name": canal["nombre"], "logo": f"{URL}/logo.png"}
    if e.get("youtube"):
        jsonld = {
            "@context": "https://schema.org", "@type": "VideoObject",
            "name": e["titulo"], "description": e.get("resumen") or e["titulo"],
            "thumbnailUrl": [url_absoluta(e["_img"])], "uploadDate": fecha_iso(e["fecha"]),
            "embedUrl": f"https://www.youtube.com/embed/{e['youtube']}",
            "url": f"{URL}/{ruta}", "inLanguage": "es", "publisher": publisher,
        }
    else:
        jsonld = {
            "@context": "https://schema.org", "@type": "Article",
            "headline": e["titulo"], "description": e.get("resumen") or e["titulo"],
            "image": [url_absoluta(e["_img"])], "datePublished": fecha_iso(e["fecha"]),
            "url": f"{URL}/{ruta}", "inLanguage": "es", "author": publisher, "publisher": publisher,
        }
    if e.get("etiquetas"):
        jsonld["keywords"] = ", ".join(e["etiquetas"])
    return pagina(f"{e['titulo']} · {canal['nombre']}", cuerpo, canal, raiz="../", descripcion=e.get("resumen", ""),
                  ruta=ruta, imagen=e["_img"], tipo_og="video.other" if e.get("youtube") else "article", jsonld=jsonld,
                  extra=COPIAR_JS)


def acerca(canal: dict) -> str:
    redes = "".join(f'<li><a href="{escape(u)}" rel="noopener">{escape(n)}</a></li>' for n, u in (
        ("YouTube · El Archivo Curioso", canal["youtube"]),
        ("Instagram · @elarchivocuriosoo", "https://www.instagram.com/elarchivocuriosoo/"),
        ("TikTok · @elarchivocurioso7", "https://www.tiktok.com/@elarchivocurioso7")))
    cuerpo = f"""<main class="ancho legal">
<a class="volver" href="index.html">← Inicio</a>
<h1>Acerca de El Archivo Curioso</h1>
<div class="fecha">{escape(canal['lema'])}</div>
<h2>Qué es este archivo</h2>
<p>El Archivo Curioso es un proyecto de divulgación en español que abre «expedientes» sobre la historia: sucesos reales tan extraños que parecen inventados, mitos que se repiten desde hace siglos, personajes olvidados y curiosidades que no suelen contarse en clase. Cada expediente se publica como vídeo o Short en YouTube y aquí, en la web, con más contexto, curiosidades y fuentes.</p>
<h2>Cómo trabajamos</h2>
<ul>
  <li><b>Fuentes primero.</b> Cada expediente se basa en fuentes que citamos al final de su página: estudios, enciclopedias de referencia, museos y obras de historiadores.</li>
  <li><b>Lo dudoso se dice.</b> Cuando una cifra o una explicación está discutida, lo indicamos en lugar de presentarla como un hecho.</li>
  <li><b>Mitos, desmontados con datos.</b> Si un dato muy repetido no aparece en las fuentes de la época, lo señalamos.</li>
  <li><b>Imágenes libres.</b> Usamos obras de dominio público o con licencias libres (sobre todo de Wikimedia Commons) y citamos su origen.</li>
  <li><b>Transparencia.</b> La narración de los vídeos usa una voz sintética, y para preparar los guiones nos ayudamos de herramientas de inteligencia artificial; los datos se contrastan con las fuentes citadas.</li>
</ul>
<h2>¿Has encontrado un error?</h2>
<p>La historia se revisa constantemente. Si crees que un expediente contiene un error, escríbenos en los comentarios del vídeo en YouTube o por mensaje privado en redes, con la fuente si la tienes, y lo revisaremos.</p>
<h2>Dónde encontrarnos</h2>
<ul>{redes}</ul>
</main>"""
    return pagina(f"Acerca de · {canal['nombre']}", cuerpo, canal, ruta="acerca.html",
                  descripcion="Qué es El Archivo Curioso, cómo elegimos y comprobamos cada expediente y cómo contactar.")


def privacidad(canal: dict) -> str:
    cuerpo = """<main class="ancho legal">
<a class="volver" href="index.html">← Inicio</a>
<h1>Política de privacidad</h1>
<div class="fecha">Última actualización: 28 de octubre de 2026</div>
<h2>1. Qué es esta herramienta</h2>
<p>"elarchivocurioso scripts" es una herramienta de uso privado que utiliza la persona responsable del canal de YouTube El Archivo Curioso para gestionar su propio canal: subir sus vídeos, completar títulos, descripciones, miniaturas, subtítulos y listas de reproducción, y consultar las estadísticas y los comentarios del canal. No es una aplicación pública ni está pensada para que la usen otras personas.</p>
<h2>2. Qué datos se usan</h2>
<p>Con el permiso que concede la persona titular de la cuenta, la herramienta accede a través de la API de YouTube a:</p>
<ul>
  <li>La información del canal (nombre, descripción, imagen y estadísticas).</li>
  <li>Los vídeos, listas de reproducción y subtítulos del canal.</li>
  <li>Los comentarios públicos recibidos en el canal, solo para leerlos.</li>
</ul>
<h2>3. Cómo se guardan</h2>
<ul>
  <li>El permiso de acceso se guarda únicamente en el ordenador de la persona titular, en el gestor de credenciales del sistema.</li>
  <li>Los datos se usan solo para gestionar el propio canal. No se venden, no se comparten con terceros y no se usan para publicidad.</li>
  <li>La herramienta no recopila datos de los espectadores del canal.</li>
</ul>
<h2>4. Esta web</h2>
<p>Esta web no usa cookies propias ni formularios. Los vídeos se muestran con el reproductor de YouTube en modo de privacidad mejorada (youtube-nocookie.com); al reproducirlos se aplica la política de privacidad de Google.</p>
<h2>5. Servicios de Google</h2>
<p>La herramienta usa los Servicios de la API de YouTube. Al ver el canal también se aplican las <a href="https://www.youtube.com/t/terms">Condiciones del Servicio de YouTube</a> y la <a href="https://policies.google.com/privacy">Política de Privacidad de Google</a>.</p>
<p>El uso de la información recibida de las API de Google cumple la <a href="https://developers.google.com/terms/api-services-user-data-policy">Política de Datos de Usuario de los Servicios de las API de Google</a>, incluidos los requisitos de uso limitado.</p>
<h2>6. Cómo retirar el acceso</h2>
<p>El acceso puede retirarse en cualquier momento desde <a href="https://myaccount.google.com/permissions">myaccount.google.com/permissions</a>.</p>
<h2>7. Contacto</h2>
<p>Para cualquier consulta sobre esta política, puedes escribir a través del <a href="CANAL">canal de YouTube</a>.</p>
</main>""".replace("CANAL", escape(canal["youtube"]))
    return pagina(f"Política de privacidad · {canal['nombre']}", cuerpo, canal, ruta="privacidad.html")


def generar() -> int:
    datos = json.loads(DATOS.read_text(encoding="utf-8-sig"))  # acepta archivos con o sin BOM
    canal = datos["canal"]
    ahora = datetime.now()
    visibles = [e for e in datos["expedientes"] if datetime.fromisoformat(e["fecha"]) <= ahora]
    visibles.sort(key=lambda e: e["fecha"], reverse=True)
    # Un mismo expediente puede aparecer dos veces (provisional sin YouTube, o vídeo subido dos veces):
    # se queda la primera entrada con YouTube y hereda el artículo y las lecturas de las otras
    por_titulo: dict[str, list[dict]] = {}
    for e in datos["expedientes"]:
        if e in visibles:
            por_titulo.setdefault(e["titulo"], []).append(e)
    for repetidas in (g for g in por_titulo.values() if len(g) > 1):
        destino = next((e for e in repetidas if e.get("youtube")), repetidas[0])
        for e in repetidas:
            if e is destino:
                continue
            for campo in ("articulo", "lecturas", "slug"):
                if e.get(campo) and not destino.get(campo):
                    destino[campo] = e[campo]
            visibles.remove(e)

    dir_min = WEB / "miniaturas"
    if dir_min.exists():
        shutil.rmtree(dir_min)
    dir_min.mkdir()
    usados: set[str] = set()
    for e in visibles:
        s = e.get("slug") or slug(e["titulo"])
        while s in usados:
            s += "-" + (e.get("youtube") or e.get("num") or "x")[:4].lower()
        e["_slug"] = s
        usados.add(s)
        # Miniatura propia si existe; si no, la de YouTube
        origen = WEB.parent / e["miniatura"] if e.get("miniatura") else None
        if origen and origen.exists():
            shutil.copyfile(origen, dir_min / f"{s}{origen.suffix.lower()}")
            e["_img"] = f"miniaturas/{s}{origen.suffix.lower()}"
        elif e.get("youtube"):
            e["_img"] = f"https://i.ytimg.com/vi/{e['youtube']}/hqdefault.jpg"
        else:
            e["_img"] = "compartir.png"

    # Enlaces entre cada episodio y sus Shorts ("de" = num del episodio)
    por_num = {e["num"]: e for e in visibles if e.get("num")}
    for e in visibles:
        episodio = por_num.get(e.get("de"))
        if episodio:
            e["_episodio"] = episodio
            episodio.setdefault("_shorts", []).append(e)

    dir_exp = WEB / "expedientes"
    if dir_exp.exists():
        shutil.rmtree(dir_exp)
    dir_exp.mkdir()
    for i, e in enumerate(visibles):
        anterior = visibles[i + 1] if i + 1 < len(visibles) else None   # más antiguo
        siguiente = visibles[i - 1] if i > 0 else None                  # más reciente
        (dir_exp / f"{e['_slug']}.html").write_text(expediente(e, anterior, siguiente, canal), encoding="utf-8")

    (WEB / "index.html").write_text(inicio(canal, visibles), encoding="utf-8")
    (WEB / "privacidad.html").write_text(privacidad(canal), encoding="utf-8")
    (WEB / "acerca.html").write_text(acerca(canal), encoding="utf-8")
    (WEB / ".nojekyll").write_text("", encoding="utf-8")
    if LOGO_ORIGEN.exists():
        shutil.copyfile(LOGO_ORIGEN, WEB / "logo.png")
    if BANNER_ORIGEN.exists():
        shutil.copyfile(BANNER_ORIGEN, WEB / "compartir.png")
    # Archivo de verificación de Google Search Console (no se debe borrar nunca)
    if canal.get("google_archivo"):
        (WEB / canal["google_archivo"]).write_text(f"google-site-verification: {canal['google_archivo']}",
                                                   encoding="utf-8")

    # Feed RSS: para lectores como Feedly o Inoreader y agregadores de noticias
    items = "".join(
        f"<item><title>{escape_xml(e['titulo'])}</title>"
        f"<link>{URL}/expedientes/{e['_slug']}.html</link>"
        f"<guid>{URL}/expedientes/{e['_slug']}.html</guid>"
        f"<pubDate>{format_datetime(datetime.fromisoformat(e['fecha']).astimezone())}</pubDate>"
        f"<description>{escape_xml(e.get('resumen', ''))}</description></item>"
        for e in visibles)
    (WEB / "feed.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        f"<title>{escape_xml(canal['nombre'])}</title><link>{URL}/</link>"
        f"<description>{escape_xml(canal['descripcion'])}</description><language>es</language>"
        f"{items}</channel></rss>\n", encoding="utf-8")

    # Mapa del sitio y robots.txt: así los buscadores encuentran todas las páginas
    hoy = date.today().isoformat()
    entradas = [(f"{URL}/", visibles[0]["fecha"][:10] if visibles else hoy)]
    entradas += [(f"{URL}/expedientes/{e['_slug']}.html", e["fecha"][:10]) for e in visibles]
    entradas.append((f"{URL}/acerca.html", hoy))
    entradas.append((f"{URL}/privacidad.html", hoy))
    (WEB / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{escape_xml(u)}</loc><lastmod>{f}</lastmod></url>\n" for u, f in entradas)
        + "</urlset>\n", encoding="utf-8")
    (WEB / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {URL}/sitemap.xml\n", encoding="utf-8")

    # Clave de IndexNow (Bing, Yandex...): un archivo con la clave en la raíz demuestra que la web es nuestra
    if not CLAVE_INDEXNOW.exists():
        CLAVE_INDEXNOW.write_text(secrets.token_hex(16), encoding="utf-8")
    clave = CLAVE_INDEXNOW.read_text(encoding="utf-8").strip()
    for viejo in WEB.glob("*.txt"):
        if re.fullmatch(r"[0-9a-f]{32}\.txt", viejo.name) and viejo.stem != clave:
            viejo.unlink()
    (WEB / f"{clave}.txt").write_text(clave, encoding="utf-8")
    ocultos = len(datos["expedientes"]) - len(visibles)
    print(f"Web generada: {len(visibles)} expedientes publicados" + (f", {ocultos} programados para más adelante" if ocultos else ""))
    return len(visibles)


def git(*args: str) -> subprocess.CompletedProcess:
    exe = shutil.which("git") or r"C:\Program Files\Git\cmd\git.exe"
    return subprocess.run([exe, *args], cwd=WEB, capture_output=True, text=True, encoding="utf-8", errors="replace")


def publicar() -> None:
    generar()
    git("add", "-A")
    if not git("status", "--porcelain").stdout.strip():
        print("No hay cambios que subir.")
        return
    r = git("commit", "-m", f"Actualizar web ({date.today().isoformat()})\n\n"
                              "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>")
    if r.returncode != 0:
        sys.exit(f"ERROR en git commit:\n{r.stderr}")
    r = git("push")
    if r.returncode != 0:
        sys.exit(f"ERROR en git push (¿hay que volver a autorizar GitHub?):\n{r.stderr}")
    print(f"Web publicada en {URL} (tarda 1-2 minutos en actualizarse).")
    avisar_buscadores()


def avisar_buscadores() -> None:
    """Avisa a Bing y otros buscadores (IndexNow) de que la web ha cambiado.
    Google no usa IndexNow: lee el sitemap desde Google Search Console."""
    clave = CLAVE_INDEXNOW.read_text(encoding="utf-8").strip()
    sitemap = (WEB / "sitemap.xml").read_text(encoding="utf-8")
    urls = re.findall(r"<loc>(.*?)</loc>", sitemap)
    # Hay que esperar a que GitHub publique esta versión (el mapa del sitio en línea igual al nuevo)
    # para que el buscador encuentre las páginas nuevas y el archivo de la clave
    for _ in range(24):
        try:
            with urllib.request.urlopen(f"{URL}/sitemap.xml?t={time.time()}", timeout=15) as r:
                if r.read().decode("utf-8") == sitemap:
                    break
        except Exception:
            pass
        time.sleep(15)
    else:
        print("AVISO: la web aún no está actualizada; no se ha avisado a los buscadores (se hará en la próxima publicación).")
        return
    cuerpo = json.dumps({"host": URL.removeprefix("https://"), "key": clave,
                         "keyLocation": f"{URL}/{clave}.txt", "urlList": urls}).encode()
    peticion = urllib.request.Request("https://api.indexnow.org/indexnow", data=cuerpo, method="POST",
                                      headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(peticion, timeout=30) as r:
            print(f"Buscadores avisados (IndexNow, respuesta {r.status}): {len(urls)} páginas.")
    except Exception as ex:
        print(f"AVISO: no se pudo avisar a los buscadores: {ex}")


if __name__ == "__main__":
    comandos = {"generar": generar, "publicar": publicar}
    if len(sys.argv) != 2 or sys.argv[1] not in comandos:
        sys.exit("Uso: python web.py generar | publicar")
    comandos[sys.argv[1]]()
