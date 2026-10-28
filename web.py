"""
web.py - Genera y publica la web de Folio 13 (antes El Archivo Curioso; elarchivocurioso.github.io).

Uso:
    python web.py generar     Rehace la web a partir de datos/expedientes.json
    python web.py publicar    Genera la web y la sube a GitHub (git commit + push)

Vista previa sin tocar la web publicada: define WEB_SALIDA=<carpeta> (y WEB_DIR=<carpeta Web> si este
archivo no está en ella) y ejecuta "generar"; la web se escribe en esa carpeta.

Para añadir un vídeo o Short, añade una entrada a datos/expedientes.json:
    {
      "youtube": "ID del vídeo",
      "tipo": "video" | "short",
      "titulo": "...",
      "tematica": "crimenes",           paranormal, crimenes, cine, fantasia, mitos, robos o desastres. Si falta, se usa
                                        la del episodio ("de") o "tematica_alt"; si no hay ninguna, la historia sale en
                                        la portada y en su página, pero en ninguna temática, y se escribe un AVISO.
      "tematica_alt": "mitos",          opcional: segunda temática, si dudamos entre dos (sale en «Si te gusta esto»)
      "mapa": [lat, lon],               opcional: dónde pasó, para el mapa de la temática
      "verdad": [{"estado": "documentado" | "discutido" | "leyenda", "texto": "..."}],
                                        opcional: el semáforo de la verdad. Solo con lo que digan las fuentes; lo dudoso,
                                        «discutido». Si no existe, no se muestra. El texto admite notas [n].
      "aprender": ["...", "..."],       opcional: «Lo que vas a aprender» (si no, salen los apartados del artículo)
      "test": [{"pregunta", "respuesta"}],  opcional: el test (si no, «¿Lo habrías creído?» con las curiosidades)
                                        Los tres últimos los rellena Promocion/importar_articulos.py desde los artículos.
      "censura": "parte del título",    opcional: lo que sale tachado (si no, se tacha el final del título)
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
La frase grande de la portada sale de "canal" → "portada" ({"antes", "tachado", "despues", "num"}); si no
existe, se usa la de Victor Lustig.
En los párrafos del artículo, «[2]» se convierte en una nota que lleva a la fuente nº 2 de "fuentes".
Dominio propio: pon "dominio": "folio13.es" en "canal" y la web se genera para ese dominio, con su archivo CNAME
(pasos completos en Canal YouTube/Posicionamiento/Dominio propio.md). Vacío = elarchivocurioso.github.io.
Las URL de las historias (expedientes/<slug>.html) no cambian nunca: las enlazan las descripciones de YouTube.
Solo usa la biblioteca estándar de Python.
"""

from __future__ import annotations

import json
import math
import os
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

WEB = Path(os.environ.get("WEB_DIR") or Path(__file__).resolve().parent)
SALIDA = Path(os.environ.get("WEB_SALIDA") or WEB)   # dónde se escribe la web (vista previa: otra carpeta)
DATOS = WEB / "datos" / "expedientes.json"
CLAVE_INDEXNOW = WEB / "datos" / "indexnow.txt"
LOGO_ORIGEN = WEB.parent / "Identidad" / "Folio 13" / "icono.png"
BANNER_ORIGEN = WEB.parent / "Identidad" / "Folio 13" / "compartir-web.png"   # banner.png reducido a 1200×675
ICONOS = ("favicon-32.png", "apple-touch-icon.png")   # hechos una vez a partir de Identidad/Folio 13/icono.png


def _dominio() -> str:
    """Dominio propio ("canal" → "dominio"), si la usuaria lo compra; si no, el de GitHub Pages."""
    try:
        return json.loads(DATOS.read_text(encoding="utf-8-sig"))["canal"].get("dominio", "").strip()
    except (OSError, ValueError, KeyError):
        return ""


DOMINIO = _dominio()
URL = f"https://{DOMINIO}" if DOMINIO else "https://elarchivocurioso.github.io"
MARCA = "Folio 13"
ANTES = "El Archivo Curioso"   # nombre anterior: sale en los datos para buscadores, para que sepan que es la misma web
# Perfiles del archivo en redes: salen en «Acerca» y en sameAs, para que Google y las IAs sepan que son la misma marca
REDES_SOCIALES = (("Instagram · @elfolio13", "https://www.instagram.com/elfolio13/"),
                  ("TikTok · @elfolio13", "https://www.tiktok.com/@elfolio13"),
                  ("Facebook · Folio 13", "https://www.facebook.com/profile.php?id=61596062008062"))
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
# Frases de la portada: cada visita muestra una al azar (solo las de expedientes ya publicados).
# Todo sale de los artículos y sus fuentes; si una cifra está discutida, se cuenta como lo que es.
PORTADAS = [
    {"num": "A004", "antes": "Una barra de hierro de seis kilos le entró por la mejilla y ",
     "tachado": "le salió por lo alto del cráneo", "despues": ". A los pocos minutos, estaba hablando."},
    {"num": "S124", "antes": "Durante días oyeron pasos en el desván. Después ",
     "tachado": "mataron a las seis personas de la granja", "despues": ". Y el asesino se quedó allí varios días."},
    {"num": "A002", "antes": "En 1919, una ola de ", "tachado": "melaza",
     "despues": " mató a 21 personas en Boston. Dos de ellas eran niños de 10 años."},
    {"num": "S123", "antes": "En 1853, un hombre confesó ", "tachado": "trece muertes",
     "despues": " en Galicia. Dijo que una maldición lo convertía en lobo."},
    {"num": "S121", "antes": "En 1898, dos leones se comieron a los obreros de un puente en Kenia. El cazador que los mató habló de ",
     "tachado": "135 víctimas", "despues": "."},
    {"num": "S125", "antes": "En diez semanas de 1888, ", "tachado": "cinco mujeres",
     "despues": " aparecieron asesinadas en Londres. Nunca se supo quién fue."},
    {"num": "S122", "antes": "La llamaron «la condesa sangrienta». Sus sirvientes confesaron ", "tachado": "bajo tortura",
     "despues": ". Tres acabaron ejecutados."},
    {"num": "S116", "antes": "El 26 de junio de 1284, ", "tachado": "130 niños",
     "despues": " siguieron a un flautista fuera de Hamelín. Desaparecieron."},
    {"num": "A009", "antes": "En 1872 apareció un barco a la deriva en mitad del Atlántico. ",
     "tachado": "No había nadie a bordo", "despues": "."},
    {"num": "A007", "antes": "En 1925 alguien ", "tachado": "vendió la Torre Eiffel",
     "despues": ". Y su víctima no lo denunció."},
]

# Logotipo: el sello rojo, copiado de Identidad/Folio 13/logo.js (opción A). Va en línea para que use las fuentes de la web.
# Los id de los arcos llevan sufijo para poder poner dos sellos en la misma página.
def sello_svg(sufijo: str = "") -> str:
    return f"""<svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Folio 13">
<defs><path id="arco-arriba{sufijo}" d="M 100,100 m -64,0 a 64,64 0 1,1 128,0"/><path id="arco-abajo{sufijo}" d="M 100,100 m -66,0 a 66,66 0 0,0 132,0"/></defs>
<g transform="rotate(-8 100 100)">
<circle cx="100" cy="100" r="88" fill="none" stroke="#C2443B" stroke-width="5"/>
<circle cx="100" cy="100" r="76" fill="none" stroke="#C2443B" stroke-width="1.5"/>
<text font-family="IBM Plex Mono, monospace" font-weight="600" font-size="14" letter-spacing="4" fill="#C2443B"><textPath href="#arco-arriba{sufijo}" startOffset="50%" text-anchor="middle">PARECE INVENTADO</textPath></text>
<text font-family="IBM Plex Mono, monospace" font-weight="600" font-size="14" letter-spacing="4" fill="#C2443B"><textPath href="#arco-abajo{sufijo}" startOffset="50%" text-anchor="middle">ESTÁ DOCUMENTADO</textPath></text>
<text x="100" y="92" text-anchor="middle" font-family="Playfair Display, Georgia, serif" font-weight="900" font-size="30" fill="#EBDDBF">FOLIO</text>
<line x1="58" y1="100" x2="142" y2="100" stroke="#EBDDBF" stroke-width="1.5"/>
<text x="100" y="138" text-anchor="middle" font-family="Playfair Display, Georgia, serif" font-weight="900" font-size="50" fill="#C2443B">13</text>
</g></svg>"""


# Versión pequeña (menos de 100 px): solo el aro y el 13
SELLO_MINI_SVG = """<svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Folio 13">
<g transform="rotate(-8 100 100)"><circle cx="100" cy="100" r="86" fill="#12100D" fill-opacity=".55" stroke="#C2443B" stroke-width="12"/>
<text x="100" y="130" text-anchor="middle" font-family="Playfair Display, Georgia, serif" font-weight="900" font-size="92" fill="#EBDDBF">13</text></g></svg>"""

# Las 7 temáticas de Folio 13 (Identidad/Folio 13/MARCA.md), en su orden. Cada historia lleva una en "tematica".
TEMATICAS = {
    "paranormal": {"nombre": "Paranormal y leyendas", "corto": "Lo que la gente juró haber visto, y lo que dicen los papeles.",
                   "intro": "Pueblos que vieron al diablo, bestias que nadie pudo cazar y un hombre que decía convertirse en "
                            "lobo. Lo que la gente juró haber visto, comparado con lo que dejaron escrito los documentos."},
    "crimenes": {"nombre": "Crímenes del pasado", "corto": "Investigaciones, juicios y errores. Sin morbo.",
                 "intro": "Casos reales contados con los datos de las investigaciones y los juicios: cómo se descubrieron, "
                          "qué se probó, qué se equivocó y qué sigue sin respuesta. Sin morbo."},
    "cine": {"nombre": "Cine maldito y perdido", "corto": "Películas que ardieron, se prohibieron o nunca debieron rodarse.",
             "intro": "Películas que un juez mandó destruir, copias que ardieron, rodajes imposibles y la historia real "
                      "detrás de los clásicos que dieron miedo a varias generaciones."},
    "fantasia": {"nombre": "Detrás de la fantasía", "corto": "La historia real detrás de dragones, alquimistas y espadas.",
                 "intro": "La historia real detrás de dragones, alquimistas, espadas y castillos: lo que de verdad hubo "
                          "detrás de los mundos de fantasía."},
    "mitos": {"nombre": "Mitos desmontados", "corto": "Lo que todos repiten y nunca pasó así.",
              "intro": "Frases que todo el mundo repite, datos que salen en clase y anécdotas que nunca pasaron así. "
                       "Cada mito, contra lo que dicen las fuentes de la época."},
    "robos": {"nombre": "Robos y golpes", "corto": "Los golpes más audaces y cómo se resolvieron.",
              "intro": "Estafas, robos imposibles y golpes que parecían perfectos, y el detalle que acabó delatando a "
                       "quienes los planearon."},
    "desastres": {"nombre": "Desastres y epidemias", "corto": "Cuando una ciudad entera se quedó sin respuesta.",
                  "intro": "Olas de melaza, volcanes que borraron un verano, tormentas solares y epidemias extrañas: "
                           "catástrofes reales y lo que la ciencia tardó años en explicar."},
}
# «Si te gusta esto»: la temática que más se le parece, cuando no hay historias con "tematica_alt"
PARECIDAS = {"paranormal": "crimenes", "crimenes": "paranormal", "cine": "paranormal", "fantasia": "mitos",
             "mitos": "desastres", "robos": "crimenes", "desastres": "mitos"}
VERDAD = {"documentado": ("ok", "Documentado"), "discutido": ("disc", "Discutido"), "leyenda": ("ley", "Leyenda")}

CSS = """
:root { --fondo:#0A0807; --tarjeta:#14100E; --tarjeta-2:#1D1714; --borde:rgba(235,221,191,.09); --borde-2:rgba(235,221,191,.2);
        --texto:#EBDDBF; --texto-2:#C9BA9B; --texto-3:#857A69; --oro:#C8A04A; --rojo:#D2463C; --sangre:#7A1610;
        --brillo:0 0 24px rgba(210,70,60,.45); --verde:#5E8C4A; --ambar:#D49A2A; --papel:#EBDDBF; --radio:14px; }
* { margin:0; padding:0; box-sizing:border-box; }
html { scroll-behavior:smooth; }
body { font-family:'Source Serif 4',Georgia,serif; background:var(--fondo); color:var(--texto);
  line-height:1.6; min-height:100vh; -webkit-font-smoothing:antialiased; overflow-x:hidden; }
::selection { background:var(--rojo); color:#fff; }
a { color:var(--texto); text-decoration-color:var(--rojo); text-decoration-thickness:1px; text-underline-offset:4px; }
a:hover { color:#fff; }
.ancho { max-width:1240px; margin:0 auto; padding-left:16px; padding-right:16px; }
.mono { font-family:'IBM Plex Mono',monospace; letter-spacing:.16em; text-transform:uppercase; }
.maquina { font-family:'Special Elite','Courier New',monospace; }
.serif { font-family:'Playfair Display',Georgia,serif; }
h1, h2, h3, h4 { font-family:'Playfair Display',Georgia,serif; letter-spacing:-.01em; }

/* Atmósfera: niebla roja que respira, grano y viñeta. No tapan clics. */
body::before { content:""; position:fixed; inset:-50%; z-index:50; pointer-events:none; opacity:.07;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  animation:grano .9s steps(6) infinite; }
body::after { content:""; position:fixed; inset:0; z-index:49; pointer-events:none;
  background:radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,.65) 100%); }
.niebla-fondo { position:fixed; inset:0; z-index:-1; pointer-events:none; overflow:hidden; }
.niebla-fondo::before, .niebla-fondo::after { content:""; position:absolute; width:70vmax; height:70vmax; border-radius:50%; filter:blur(80px); opacity:.16; }
.niebla-fondo::before { background:#7A1610; left:-20vmax; top:-25vmax; animation:respira 18s ease-in-out infinite alternate; }
.niebla-fondo::after { background:#3B2418; right:-25vmax; bottom:-30vmax; animation:respira 22s ease-in-out infinite alternate-reverse; }
@keyframes respira { from { transform:translate(0,0) scale(1); } to { transform:translate(8vmax,6vmax) scale(1.15); } }
@keyframes grano { 0%{transform:translate(0,0)} 20%{transform:translate(-3%,2%)} 40%{transform:translate(2%,-3%)}
  60%{transform:translate(-2%,-1%)} 80%{transform:translate(3%,3%)} 100%{transform:translate(0,0)} }

/* Aparecer al hacer scroll (solo si el script funciona: si no, todo se ve) */
.con-js .aparece { opacity:0; transform:translateY(22px); transition:opacity .8s ease, transform .8s cubic-bezier(.2,.7,.2,1); }
.con-js .aparece.visto { opacity:1; transform:none; }

/* Logotipo: el sello de Folio 13 */
.logo { --t:64px; flex:none; display:block; width:var(--t); height:var(--t); }
.logo svg { display:block; width:100%; height:100%; overflow:visible; }

/* Lo censurado: barra negra que se revela al pasar el ratón, al tocar o con el teclado (el texto sigue en el HTML) */
.tachado { color:transparent; padding:0 .03em; cursor:pointer; -webkit-box-decoration-break:clone; box-decoration-break:clone;
  background:repeating-linear-gradient(-45deg,#000 0 6px,#231A16 6px 9px) center / 100% .92em no-repeat; position:relative;
  transition:color .45s ease .1s, background-size .45s cubic-bezier(.6,0,.2,1), text-shadow .45s; animation:interferencia 7s infinite; }
.tachado:hover, .tachado:focus-visible, .tachado.revelado, a:hover .tachado, a:focus-visible .tachado {
  color:#FF5A4C; background-size:100% 0; text-shadow:0 0 22px rgba(255,70,60,.55); animation:none; }
.tachado:focus-visible { outline:2px solid var(--rojo); outline-offset:3px; }
@keyframes interferencia { 0%,91%,100% { opacity:1; } 92% { opacity:.35; } 93% { opacity:1; } 95% { opacity:.6; } 96% { opacity:1; } }

/* Cabecera de cristal */
header { position:sticky; top:0; z-index:40; background:rgba(10,8,7,.62);
  backdrop-filter:blur(14px) saturate(1.2); -webkit-backdrop-filter:blur(14px) saturate(1.2); border-bottom:1px solid var(--borde); }
header .ancho { display:flex; align-items:center; gap:10px; height:64px; }
header .nombre { font-family:'Playfair Display',Georgia,serif; font-weight:900; font-size:22px; color:var(--texto); text-decoration:none; line-height:1; white-space:nowrap; }
header .nombre em { color:var(--rojo); font-style:normal; text-shadow:var(--brillo); }
header nav { margin-left:auto; display:flex; align-items:center; gap:22px; }
header nav a { font-family:'IBM Plex Mono',monospace; color:var(--texto-2); text-decoration:none; font-size:12px; letter-spacing:.12em; text-transform:uppercase; transition:color .2s; }
header nav a:hover { color:#fff; }
.sorprendeme { font:600 12px 'IBM Plex Mono',monospace; letter-spacing:.08em; color:#fff; background:var(--rojo); border:1px solid var(--rojo);
  border-radius:999px; padding:8px 14px; cursor:pointer; text-decoration:none; white-space:nowrap; text-transform:uppercase; box-shadow:var(--brillo); }
.sorprendeme:hover { background:#fff; color:#000; border-color:#fff; }
@media (max-width:960px) { header nav .solo-ancho { display:none; } }
@media (max-width:720px) { header .ancho { height:58px; } header .nombre { font-size:19px; } header nav { gap:14px; } }
@media (max-width:400px) { header .nombre { display:none; } }

/* Botones */
.botones { display:flex; flex-wrap:wrap; gap:10px; margin-top:28px; }
.boton { display:inline-flex; align-items:center; gap:8px; font:600 13px 'IBM Plex Mono',monospace; letter-spacing:.06em; text-transform:uppercase;
  text-decoration:none; padding:14px 22px; border-radius:999px; background:var(--rojo); color:#fff; border:1px solid var(--rojo); cursor:pointer;
  box-shadow:var(--brillo); transition:transform .2s, background .2s, color .2s; }
.boton:hover { background:#fff; border-color:#fff; color:#000; transform:translateY(-2px); }
.boton.secundario { background:rgba(255,255,255,.04); color:var(--texto); border-color:var(--borde-2); box-shadow:none; backdrop-filter:blur(6px); }
.boton.secundario:hover { border-color:#fff; background:#fff; color:#000; }

/* Portada: el caso a oscuras y una linterna que lo descubre */
.portada { position:relative; min-height:calc(100svh - 64px); display:flex; align-items:center; padding-top:56px; padding-bottom:64px; isolation:isolate; }
.escena { position:absolute; inset:0 -50vw; z-index:-1; overflow:hidden; pointer-events:none; }
.escena .foto, .escena .foto-luz { position:absolute; inset:0; background:center 30%/cover no-repeat; }
.escena .foto { filter:grayscale(1) contrast(1.2) brightness(.16) blur(2px); transform:scale(1.05); }
.escena .foto-luz { filter:grayscale(.3) sepia(.4) contrast(1.15) brightness(.55) saturate(1.3);
  -webkit-mask-image:radial-gradient(circle 240px at var(--x,65%) var(--y,45%), #000 0, rgba(0,0,0,.6) 45%, transparent 75%);
  mask-image:radial-gradient(circle 240px at var(--x,65%) var(--y,45%), #000 0, rgba(0,0,0,.6) 45%, transparent 75%); }
.escena::after { content:""; position:absolute; inset:0; background:linear-gradient(90deg,var(--fondo) 0%,rgba(10,8,7,.75) 30%,rgba(10,8,7,.2) 70%,rgba(10,8,7,.6) 100%),
  linear-gradient(0deg,var(--fondo) 0%,transparent 30%); }
.portada-grid { display:grid; grid-template-columns:minmax(0,1.35fr) minmax(0,1fr); gap:48px; align-items:end; width:100%; }
.etiqueta-caso { display:inline-flex; align-items:center; gap:10px; font-family:'IBM Plex Mono',monospace; color:var(--rojo); letter-spacing:.25em;
  font-size:12px; text-transform:uppercase; }
.etiqueta-caso::before { content:""; width:9px; height:9px; border-radius:50%; background:var(--rojo); box-shadow:var(--brillo); animation:latido 1.6s ease-in-out infinite; }
@keyframes latido { 0%,100% { opacity:1; transform:scale(1); } 50% { opacity:.35; transform:scale(.7); } }
.portada h1 { font-weight:900; font-size:clamp(38px,6.2vw,86px); line-height:1.02; letter-spacing:-.025em; margin:18px 0 18px; max-width:15ch;
  text-shadow:0 4px 40px rgba(0,0,0,.8); }
.portada h1 a { color:inherit; text-decoration:none; }
.portada .desc { color:var(--texto-2); font-size:19px; max-width:560px; }
.portada .pista { color:var(--texto-3); font-size:12px; margin-top:12px; }
.portada .lateral-portada { display:flex; flex-direction:column; gap:16px; align-items:stretch; }
.portada .sello-grande { --t:140px; margin-left:auto; animation:flota 6s ease-in-out infinite; filter:drop-shadow(0 0 30px rgba(210,70,60,.35)); }
@keyframes flota { 0%,100% { transform:translateY(0) rotate(0); } 50% { transform:translateY(-8px) rotate(2deg); } }
.contador { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
.contador div { background:rgba(20,16,14,.6); backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); border:1px solid var(--borde); border-radius:var(--radio); padding:16px 8px; text-align:center; }
.contador b { display:block; font-family:'Playfair Display',serif; font-size:36px; line-height:1.05; color:#fff; }
.contador span { font-family:'IBM Plex Mono',monospace; font-size:10px; color:var(--texto-3); letter-spacing:.16em; }
.leidos { font-family:'IBM Plex Mono',monospace; font-size:12px; color:var(--texto-3); text-align:right; }
.bajar { position:absolute; left:50%; bottom:18px; transform:translateX(-50%); color:var(--texto-3); font-size:11px; text-decoration:none; text-align:center; }
.bajar::after { content:""; display:block; width:1px; height:34px; margin:8px auto 0; background:linear-gradient(var(--rojo),transparent); animation:goteo 2s ease-in infinite; }
@keyframes goteo { from { transform:scaleY(0); transform-origin:top; } 60% { transform:scaleY(1); transform-origin:top; } to { transform:scaleY(1); opacity:0; } }
@media (max-width:860px) { .portada { min-height:auto; padding-top:44px; } .portada-grid { grid-template-columns:1fr; gap:30px; }
  .portada .sello-grande { display:none; } .leidos { text-align:left; } .bajar { display:none; } }
@media (max-width:1272px) { .escena { inset:0 -16px; } }

/* Secciones */
.seccion { padding-top:44px; padding-bottom:64px; }
.seccion-cab { display:flex; align-items:flex-end; justify-content:space-between; gap:16px; flex-wrap:wrap; margin-bottom:24px; }
.seccion-cab h2 { font-weight:900; font-size:clamp(28px,3.6vw,40px); line-height:1.05; }
.seccion-cab .kicker { display:block; font-family:'IBM Plex Mono',monospace; font-size:11px; letter-spacing:.2em; color:var(--rojo); text-transform:uppercase; margin-bottom:8px; }
.seccion-cab .cuenta { color:var(--texto-3); font-size:15px; }
.filtros { display:flex; gap:6px; flex-wrap:wrap; }
.filtros button { font:500 12px 'IBM Plex Mono',monospace; cursor:pointer; padding:7px 14px; border-radius:999px; text-transform:uppercase; letter-spacing:.08em;
  border:1px solid var(--borde-2); background:transparent; color:var(--texto-2); transition:all .2s; }
.filtros button:hover { border-color:#fff; color:#fff; }
.filtros button.activo { background:#fff; color:#000; border-color:#fff; }

/* Tarjetas: la foto arriba (entera, sin cortar), el texto debajo */
.rejilla { display:grid; grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); gap:18px; }
.ficha { --acento:var(--rojo); position:relative; display:flex; flex-direction:column; border-radius:var(--radio); overflow:hidden;
  text-decoration:none; color:var(--texto); background:linear-gradient(180deg,var(--tarjeta),#0E0B0A); border:1px solid var(--borde);
  transition:transform .4s cubic-bezier(.2,.7,.2,1), border-color .4s, box-shadow .4s; height:100%; }
.ficha .foto { position:relative; aspect-ratio:16/9; overflow:hidden; background:var(--tarjeta-2); }
.ficha .img { display:block; width:100%; height:100%; object-fit:cover; filter:grayscale(.85) contrast(1.1) brightness(.62) sepia(.15);
  transition:transform 1.2s cubic-bezier(.2,.7,.2,1), filter .6s; }
.ficha .foto::after { content:""; position:absolute; inset:0; background:linear-gradient(180deg,transparent 55%,rgba(14,11,10,.85)),
  radial-gradient(circle at 50% 120%, var(--acento), transparent 65%); opacity:.9; mix-blend-mode:normal; pointer-events:none; }
.ficha:hover, .ficha:focus-visible { transform:translateY(-6px); border-color:var(--acento); box-shadow:0 24px 60px -24px rgba(0,0,0,.95), 0 0 30px -12px var(--acento); color:var(--texto); }
.ficha:hover .img, .ficha:focus-visible .img { transform:scale(1.07); filter:grayscale(.15) contrast(1.05) brightness(.85) sepia(.15); animation:parpadeo .9s steps(1) 1; }
@keyframes parpadeo { 0% { filter:brightness(.2) grayscale(1); } 12% { filter:brightness(.9) grayscale(.2); } 18% { filter:brightness(.15) grayscale(1); } 30% { filter:none; } }
.ficha:focus-visible { outline:2px solid #fff; outline-offset:2px; }
.ficha .tipo { position:absolute; right:10px; top:10px; z-index:1; padding:3px 9px; font:600 10px 'IBM Plex Mono',monospace; letter-spacing:.14em;
  background:rgba(0,0,0,.6); backdrop-filter:blur(6px); color:#fff; border-radius:999px; border:1px solid rgba(255,255,255,.18); }
.ficha .leido-marca { position:absolute; left:10px; top:10px; z-index:1; padding:3px 9px; font:600 10px 'IBM Plex Mono',monospace; letter-spacing:.14em;
  background:var(--oro); color:#000; border-radius:999px; display:none; }
.ficha.leido .leido-marca { display:block; }
.ficha .puesto { position:absolute; left:12px; bottom:4px; z-index:1; font-family:'Playfair Display',serif; font-weight:900; font-size:52px; line-height:1;
  color:var(--rojo); text-shadow:0 0 24px rgba(0,0,0,.9), var(--brillo); }
.ficha .txt { padding:14px 16px 18px; display:flex; flex-direction:column; gap:8px; flex:1; }
.ficha .num { color:var(--acento); font-size:11px; }
.ficha h3 { font-weight:700; font-size:19px; line-height:1.22; }
.ficha .meta { font-size:13px; color:var(--texto-3); margin-top:auto; }
/* Filas que se deslizan en horizontal (lo último, cada temática, el Top 10) */
.fila, .fila-top { display:grid; grid-auto-flow:column; grid-auto-columns:minmax(250px,280px); gap:16px; overflow-x:auto; overflow-y:hidden;
  padding:8px 2px 16px; scroll-snap-type:x mandatory; scrollbar-width:thin; scrollbar-color:var(--rojo) transparent; }
.fila .ficha, .fila-top .ficha { scroll-snap-align:start; }
.fila-mas { display:flex; align-items:center; justify-content:center; border:1px dashed var(--borde-2); border-radius:var(--radio); min-height:200px;
  text-decoration:none; font-family:'IBM Plex Mono',monospace; font-size:12px; letter-spacing:.12em; text-transform:uppercase; color:var(--texto-2); scroll-snap-align:start; }
.fila-mas:hover { border-color:var(--rojo); color:#fff; }
.cuenta a, .ver-todo { color:var(--rojo); text-decoration:none; font-family:'IBM Plex Mono',monospace; font-size:12px; letter-spacing:.1em; text-transform:uppercase; }
.ver-todo:hover { color:#fff; }
.bloque-top { padding-bottom:24px; }
.fila-tema { padding-top:26px; padding-bottom:10px; }
.fila-tema .seccion-cab { margin-bottom:12px; }
.fila-tema h2 { font-size:clamp(24px,3vw,32px) !important; }
.fila-tema .kicker { color:var(--t-acento) !important; }
.etiqueta-tema { align-self:flex-start; font:600 10px 'IBM Plex Mono',monospace; letter-spacing:.12em; text-transform:uppercase;
  color:var(--acento); background:rgba(0,0,0,.45); border:1px solid currentColor; border-radius:999px; padding:2px 9px; }
.semaforo { display:inline-flex; gap:4px; flex-wrap:wrap; }
.semaforo em, .verdad em { font-style:normal; font-family:'IBM Plex Mono',monospace; font-size:10px; padding:2px 7px; border-radius:999px; white-space:nowrap; }
.ok { background:rgba(94,140,74,.25); color:#b4dc9c; }
.disc { background:rgba(212,154,42,.22); color:#f4c96e; }
.ley { background:rgba(210,70,60,.25); color:#ff9f95; }
.vacio { text-align:center; padding:40px 16px 80px; color:var(--texto-2); }
.vacio .logo { --t:90px; margin:0 auto 18px; }
.chips { display:flex; flex-wrap:wrap; gap:8px; }
.chips a { font-size:14px; color:var(--texto-2); text-decoration:none; padding:6px 13px; border:1px solid var(--borde-2); border-radius:999px; transition:all .2s; }
.chips a:hover { color:#000; border-color:#fff; background:#fff; }
.chips a small { color:var(--texto-3); }
.chips a:hover small { color:#000; }

/* Temáticas: cada una con su ambiente */
.t-paranormal { --t-fondo:#121B1A; --t-cab:#0D1615; --t-cuerpo:#080F0E; --t-texto:#D4EAE3; --t-texto-2:#A2C2B9; --t-acento:#5FE0C2; --t-borde:rgba(95,224,194,.18);
  --t-textura:radial-gradient(ellipse at 80% 20%,rgba(95,224,194,.14),transparent 60%),radial-gradient(ellipse at 10% 90%,rgba(95,224,194,.08),transparent 50%); }
.t-crimenes { --t-fondo:#1F0F0D; --t-cab:#180A08; --t-cuerpo:#0F0605; --t-texto:#F5D6D0; --t-texto-2:#D7A9A1; --t-acento:#FF5A4C; --t-borde:rgba(255,90,76,.2);
  --t-textura:repeating-linear-gradient(-35deg,transparent 0 26px,rgba(255,90,76,.05) 26px 28px); }
.t-cine { --t-fondo:#161616; --t-cab:#101010; --t-cuerpo:#0A0A0A; --t-texto:#EEEAE0; --t-texto-2:#BDB7A9; --t-acento:#F2DFA9; --t-borde:rgba(242,223,169,.18);
  --t-textura:repeating-linear-gradient(90deg,transparent 0 22px,rgba(255,255,255,.045) 22px 24px); }
.t-fantasia { --t-fondo:#17122A; --t-cab:#110C20; --t-cuerpo:#0B0815; --t-texto:#E2DAFA; --t-texto-2:#B3A9D6; --t-acento:#B49CFF; --t-borde:rgba(180,156,255,.2);
  --t-textura:radial-gradient(circle at 20% 30%,rgba(180,156,255,.2) 0 1px,transparent 2px),radial-gradient(circle at 70% 60%,rgba(180,156,255,.15) 0 1px,transparent 2px); }
.t-mitos { --t-fondo:#211A0B; --t-cab:#1A1407; --t-cuerpo:#110D04; --t-texto:#F5E6BF; --t-texto-2:#D2C18F; --t-acento:#F2C14E; --t-borde:rgba(242,193,78,.2);
  --t-textura:repeating-linear-gradient(0deg,transparent 0 30px,rgba(242,193,78,.06) 30px 31px); }
.t-robos { --t-fondo:#0F1923; --t-cab:#0B131B; --t-cuerpo:#070C12; --t-texto:#D3E4F3; --t-texto-2:#A2B9CE; --t-acento:#6CB8FF; --t-borde:rgba(108,184,255,.2);
  --t-textura:linear-gradient(rgba(108,184,255,.06) 1px,transparent 1px) 0 0/24px 24px,linear-gradient(90deg,rgba(108,184,255,.06) 1px,transparent 1px) 0 0/24px 24px; }
.t-desastres { --t-fondo:#1C1F0D; --t-cab:#161809; --t-cuerpo:#0E1005; --t-texto:#E8EDC8; --t-texto-2:#BFC69A; --t-acento:#D9E85A; --t-borde:rgba(217,232,90,.2);
  --t-textura:radial-gradient(ellipse at 70% 0%,rgba(217,232,90,.12),transparent 55%),radial-gradient(ellipse at 0% 100%,rgba(0,0,0,.35),transparent 60%); }
.rejilla-temas { display:grid; grid-template-columns:repeat(4,1fr); grid-auto-rows:minmax(210px,auto); gap:14px; }
.rejilla-temas .tema:nth-child(1) { grid-column:span 2; min-height:250px; }
.tema { border-radius:var(--radio); padding:20px; min-height:210px; display:flex; flex-direction:column; justify-content:space-between; position:relative; overflow:hidden; isolation:isolate;
  border:1px solid var(--t-borde); background:var(--t-textura), var(--t-fondo); color:var(--t-texto); text-decoration:none;
  transition:transform .4s cubic-bezier(.2,.7,.2,1), border-color .4s, box-shadow .4s; }
.tema .fondo-img { position:absolute; inset:0; z-index:-1; background:center/cover no-repeat; opacity:.42; filter:grayscale(.85) contrast(1.15) brightness(.6);
  transition:transform 1.2s cubic-bezier(.2,.7,.2,1), opacity .5s; }
.tema::before { content:""; position:absolute; inset:0; z-index:-1; background:linear-gradient(160deg, transparent 0%, var(--t-fondo) 75%); }
.tema:hover { transform:translateY(-5px); border-color:var(--t-acento); color:var(--t-texto); box-shadow:0 0 40px -10px var(--t-acento); }
.tema:hover .fondo-img { transform:scale(1.08); opacity:.6; }
.tema .num { font-family:'IBM Plex Mono',monospace; font-size:11px; color:var(--t-acento); letter-spacing:.16em; }
.tema h3 { font-size:clamp(22px,2.4vw,30px); margin:8px 0 6px; line-height:1.08; }
.tema p { font-size:15px; opacity:.88; max-width:40ch; }
.tema .pie { font-family:'IBM Plex Mono',monospace; font-size:11px; margin-top:14px; color:var(--t-acento); letter-spacing:.08em; display:flex; justify-content:space-between; }
.tema .pie::after { content:"→"; transition:transform .3s; }
.tema:hover .pie::after { transform:translateX(6px); }
.rejilla-redes { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:14px; }
@media (max-width:980px) { .rejilla-temas { grid-template-columns:repeat(2,1fr); } }
@media (max-width:560px) { .rejilla-temas { grid-template-columns:1fr; } .rejilla-temas .tema:nth-child(1) { grid-column:auto; } }

/* Página de una temática */
.pagina-tema { color:var(--t-texto); background:linear-gradient(180deg, var(--t-cuerpo), var(--fondo) 60%); }
.pagina-tema .ficha { --acento:var(--t-acento); border-color:var(--t-borde); }
.tema-cab { position:relative; overflow:hidden; isolation:isolate; background:var(--t-textura), var(--t-cab); border-bottom:1px solid var(--t-borde); }
.tema-cab .fondo-img { position:absolute; inset:0; z-index:-1; background:center 30%/cover no-repeat; opacity:.3; filter:grayscale(.8) contrast(1.2) brightness(.55) blur(1px); }
.tema-cab::after { content:""; position:absolute; inset:0; z-index:-1; background:linear-gradient(90deg, var(--t-cab) 20%, transparent), linear-gradient(0deg, var(--t-cab), transparent 50%); }
.tema-cab .ancho { padding-top:72px; padding-bottom:48px; }
.tema-cab .mono { font-size:12px; color:var(--t-acento); }
.tema-cab h1 { font-size:clamp(40px,7vw,80px); font-weight:900; line-height:1; margin:10px 0 14px; letter-spacing:-.025em; }
.tema-cab p { max-width:680px; color:var(--t-texto-2); font-size:19px; }
.tema-cuerpo { display:grid; grid-template-columns:minmax(0,1fr) 320px; gap:28px; padding-top:32px; padding-bottom:64px; }
.lateral { display:flex; flex-direction:column; gap:14px; }
.caja { background:rgba(20,16,14,.55); backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); border:1px solid var(--t-borde, var(--borde)); border-radius:var(--radio); padding:16px; }
.caja h2 { margin:0 0 12px; font-family:'IBM Plex Mono',monospace; font-weight:400; font-size:11px; letter-spacing:.18em; color:var(--t-acento, var(--rojo)); text-transform:uppercase; }
.mapa { display:block; width:100%; height:auto; border-radius:10px; background:rgba(0,0,0,.35); }
.mapa .tierra { fill:rgba(255,255,255,.12); stroke:rgba(255,255,255,.18); stroke-width:.3; }
.mapa a circle { fill:var(--t-acento, var(--rojo)); stroke:rgba(0,0,0,.6); stroke-width:.6; }
.mapa a:hover circle, .mapa a:focus circle { fill:#fff; }
.linea { list-style:none; display:flex; flex-direction:column; gap:0; font-size:14px; position:relative; }
.linea li { display:flex; gap:12px; padding:6px 0; border-left:1px solid var(--t-borde, var(--borde)); padding-left:14px; position:relative; }
.linea li::before { content:""; position:absolute; left:-4px; top:13px; width:7px; height:7px; border-radius:50%; background:var(--t-acento, var(--rojo)); }
.linea b { font-family:'IBM Plex Mono',monospace; color:var(--t-acento, var(--oro)); font-weight:400; min-width:64px; font-size:12px; padding-top:2px; }
.linea a { text-decoration:none; }
.linea a:hover { text-decoration:underline; }
.parecidos { list-style:none; display:flex; flex-direction:column; gap:10px; font-size:15px; }
.parecidos small { display:block; font-family:'IBM Plex Mono',monospace; font-size:10px; letter-spacing:.12em; color:var(--t-texto-2, var(--texto-3)); text-transform:uppercase; }
.proximamente { padding:44px 20px; border:1px dashed var(--t-borde); border-radius:var(--radio); text-align:center; color:var(--t-texto-2); }
@media (max-width:900px) { .tema-cuerpo { grid-template-columns:1fr; } }

/* Página de una historia: oscura, con la imagen del caso arriba y las fuentes en papel */
.exposicion { position:fixed; left:0; top:0; height:3px; width:0; z-index:60; background:var(--rojo); box-shadow:var(--brillo); }
.hist-cab { position:relative; overflow:hidden; isolation:isolate; border-bottom:1px solid var(--borde); }
.hist-cab .fondo-img { position:absolute; inset:-20px; z-index:-2; background:center 30%/cover no-repeat;
  filter:grayscale(.85) contrast(1.2) brightness(.35) blur(2px); transform:scale(1.04); }
.hist-cab::after { content:""; position:absolute; inset:0; z-index:-1;
  background:linear-gradient(0deg, var(--fondo) 0%, rgba(10,8,7,.6) 45%, rgba(10,8,7,.35) 100%), radial-gradient(ellipse at 20% 100%, rgba(122,22,16,.35), transparent 60%); }
.hist-cab .ancho { padding-top:72px; padding-bottom:38px; }
.miga { font-size:12px; color:var(--texto-2); }
.miga a { color:inherit; text-decoration:none; }
.miga a:hover { color:#fff; }
.hist-cab h1 { font-weight:900; font-size:clamp(34px,5.6vw,68px); line-height:1.03; margin:14px 0 14px; max-width:20ch; letter-spacing:-.025em; text-shadow:0 4px 30px rgba(0,0,0,.8); }
.hist-cab .sub { font-style:italic; color:var(--texto-2); font-size:20px; margin:0 0 18px; max-width:760px; }
.datos { display:flex; flex-wrap:wrap; gap:6px 20px; font-size:14px; color:var(--texto-3); }
.datos b { color:var(--texto-2); font-weight:600; }
.hist .ancho { padding-top:34px; padding-bottom:64px; }
.hist-grid { display:grid; grid-template-columns:minmax(0,1fr) 310px; gap:40px; align-items:start; }
.hist-texto { max-width:740px; }
.hist-lado { position:sticky; top:84px; display:flex; flex-direction:column; gap:14px; }
.aprender { background:linear-gradient(135deg, rgba(210,70,60,.1), rgba(20,16,14,.6)); border:1px dashed rgba(210,70,60,.55); border-radius:var(--radio); padding:18px 20px; margin-bottom:28px; }
.aprender h2, .verdad h2, .fuentes-caja h2 { margin:0 0 10px; font-family:'IBM Plex Mono',monospace; font-weight:400; font-size:12px; letter-spacing:.18em; color:var(--rojo); text-transform:uppercase; }
.aprender ol { padding-left:22px; }
.aprender li { margin:4px 0; font-size:17px; }
.aprender li::marker { color:var(--rojo); font-family:'IBM Plex Mono',monospace; }
.aprender li a { text-decoration:none; }
.aprender li a:hover { text-decoration:underline; }
.aprender .meta { font-size:11px; color:var(--texto-3); margin-top:12px; }
.reproductor { position:relative; width:100%; aspect-ratio:16/9; overflow:hidden; background:#000; border-radius:var(--radio); box-shadow:0 30px 80px -30px rgba(0,0,0,.95), 0 0 0 1px var(--borde); }
.reproductor.short { max-width:340px; aspect-ratio:9/16; margin:0 auto; }
.reproductor iframe { position:absolute; inset:0; width:100%; height:100%; border:0; }
.ver-yt { margin-top:10px; text-align:center; font-size:14px; }
.bloque { margin-top:40px; }
.bloque h2 { font-weight:700; font-size:29px; margin-bottom:14px; line-height:1.15; }
.bloque p { font-size:19px; color:#DCCFB3; }
.texto p, .articulo p { margin-bottom:18px; font-size:19px; line-height:1.72; color:#DCCFB3; }
#s0 p:first-child::first-letter { float:left; font-family:'Playfair Display',serif; font-weight:900; font-size:76px; line-height:.85;
  padding:6px 12px 0 0; color:var(--rojo); text-shadow:var(--brillo); }
.articulo p:last-child { margin-bottom:0; }
.articulo b { color:#fff; }
sup.nota-fuente a { font-family:'IBM Plex Mono',monospace; font-size:11px; background:var(--papel); color:#1a140e; padding:1px 6px; border-radius:999px; text-decoration:none; margin-left:2px; }
sup.nota-fuente a:hover { background:var(--rojo); color:#fff; }
.curiosidades { list-style:none; display:flex; flex-direction:column; gap:10px; counter-reset:c; }
.curiosidades li { position:relative; padding:14px 16px 14px 54px; background:var(--tarjeta); border:1px solid var(--borde); border-radius:var(--radio); font-size:17px; }
.curiosidades li::before { content:counter(c,decimal-leading-zero); counter-increment:c; position:absolute; left:16px; top:15px;
  font-family:'IBM Plex Mono',monospace; color:var(--rojo); font-size:13px; }
.verdad { background:rgba(20,16,14,.7); border:1px solid var(--borde); border-radius:var(--radio); padding:16px; }
.verdad li { display:flex; flex-direction:column; gap:5px; font-size:15px; margin:10px 0; list-style:none; padding-bottom:10px; border-bottom:1px solid var(--borde); }
.verdad li:last-child { border-bottom:0; padding-bottom:0; }
.verdad li em { align-self:flex-start; }
/* Las fuentes, como una hoja de papel prendida al expediente */
.fuentes-caja { background:var(--papel); color:#221C14; border-radius:6px; padding:18px 16px 16px; font-size:14px; transform:rotate(-.6deg);
  box-shadow:0 18px 40px -18px rgba(0,0,0,.9); position:relative; }
.fuentes-caja::before { content:""; position:absolute; top:-8px; left:50%; width:70px; height:18px; transform:translateX(-50%) rotate(2deg); background:rgba(200,160,74,.55); }
.fuentes-caja h2 { color:#8C3A2E; }
.fuentes-caja a { color:#221C14; text-decoration-color:#8C3A2E; }
.fuentes-caja ol { padding-left:20px; }
.fuentes-caja li { margin:6px 0; word-break:break-word; }
.fuentes-caja li:target { background:rgba(210,70,60,.25); }
.fuentes li { margin:6px 0 6px 20px; color:var(--texto-2); }
.hist-lado .chips a { font-size:13px; }
.quiz { margin-top:44px; padding:24px; border-radius:var(--radio); background:linear-gradient(160deg, rgba(122,22,16,.18), rgba(20,16,14,.8)); border:1px solid var(--borde); }
.quiz h2 { font-size:30px; margin-bottom:6px; }
.quiz .pregunta { margin:18px 0 10px; font-size:18px; }
.opciones { display:flex; gap:10px; flex-wrap:wrap; }
.opciones button { font:600 12px 'IBM Plex Mono',monospace; letter-spacing:.06em; text-transform:uppercase; border:1px solid var(--borde-2); border-radius:999px;
  padding:9px 16px; background:transparent; color:var(--texto); cursor:pointer; transition:all .2s; }
.opciones button:hover { border-color:#fff; background:#fff; color:#000; }
.opciones button[disabled] { cursor:default; opacity:.45; background:transparent; color:var(--texto); border-color:var(--borde-2); }
.opciones button.elegida { opacity:1; border-color:var(--rojo); background:var(--rojo); color:#fff; }
.quiz .respuesta { margin-top:10px; font-size:16px; color:#b4dc9c; display:none; }
.quiz .respuesta.vista { display:block; animation:aparecer .5s ease; }
@keyframes aparecer { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:none; } }
.quiz .marcador { margin-top:18px; font-family:'IBM Plex Mono',monospace; font-size:13px; color:#fff; }
.progreso { font-family:'IBM Plex Mono',monospace; font-size:12px; color:var(--texto-3); margin-top:18px; display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.progreso .barra { display:inline-block; height:6px; width:180px; background:rgba(255,255,255,.08); border-radius:999px; position:relative; overflow:hidden; }
.progreso .barra i { position:absolute; left:0; top:0; bottom:0; width:0; background:var(--rojo); box-shadow:var(--brillo); }
.relacionado { padding:14px 16px; border:1px solid var(--borde); border-left:3px solid var(--rojo); background:var(--tarjeta); border-radius:10px; margin-top:16px; }
.relacionado p { font-size:16px; }
.sabes-demasiado { margin-top:56px; padding:48px 20px; text-align:center; border-radius:var(--radio); position:relative; overflow:hidden;
  background:radial-gradient(ellipse at 50% 120%, rgba(210,70,60,.35), transparent 60%), var(--tarjeta); border:1px solid var(--borde); }
.sabes-demasiado p.grande { font-family:'Playfair Display',serif; font-style:italic; font-weight:900; font-size:clamp(30px,5vw,46px); }
.sabes-demasiado p.peque { color:var(--texto-3); font-size:16px; margin:8px 0 22px; }
.compartir { margin-top:36px; padding:20px 16px; border:1px solid var(--borde); background:var(--tarjeta); text-align:center; border-radius:var(--radio); }
.compartir p { margin-bottom:12px; color:var(--texto-2); }
.compartir div { display:flex; flex-wrap:wrap; gap:8px; justify-content:center; }
.compartir a, .compartir button { font:500 12px 'IBM Plex Mono',monospace; text-transform:uppercase; letter-spacing:.06em; cursor:pointer; padding:8px 14px; border-radius:999px;
  border:1px solid var(--borde-2); background:transparent; color:var(--texto); text-decoration:none; transition:all .2s; }
.compartir a:hover, .compartir button:hover { border-color:#fff; background:#fff; color:#000; }
.navegacion { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:36px; }
.navegacion a { display:block; padding:16px 18px; border:1px solid var(--borde); border-radius:var(--radio); text-decoration:none; color:var(--texto); font-size:17px;
  font-family:'Playfair Display',serif; transition:all .3s; background:var(--tarjeta); }
.navegacion a small { display:block; color:var(--rojo); font-size:11px; margin-bottom:6px; font-family:'IBM Plex Mono',monospace; text-transform:uppercase; letter-spacing:.12em; }
.navegacion a:hover { border-color:var(--rojo); transform:translateY(-2px); }
.navegacion .sig { text-align:right; grid-column:2; }
@media (max-width:960px) { .hist-grid { grid-template-columns:1fr; } .hist-lado { position:static; } .fuentes-caja { transform:none; } }
@media (max-width:600px) { .navegacion { grid-template-columns:1fr; } .navegacion .sig { grid-column:auto; } .hist-cab .ancho { padding-top:48px; } }

/* Buscar */
.buscador { width:100%; font:500 20px 'Source Serif 4',Georgia,serif; padding:16px 22px; border-radius:999px; border:1px solid var(--borde-2);
  background:rgba(20,16,14,.7); color:var(--texto); margin:10px 0 24px; }
.buscador:focus { outline:2px solid var(--rojo); outline-offset:2px; }

/* Texto legal y genérico */
.legal { padding-top:44px; padding-bottom:72px; max-width:780px; }
.legal h1 { font-weight:900; font-size:clamp(34px,6vw,54px); margin-bottom:6px; line-height:1.05; }
.legal .fecha { font-size:16px; color:var(--texto-3); margin-bottom:24px; font-style:italic; }
.legal h2 { color:var(--rojo); font-weight:700; font-size:22px; margin:30px 0 8px; }
.legal p, .legal li { font-size:17px; color:var(--texto-2); }
.legal ul { padding-left:22px; }
.lectura { max-width:780px; margin:0 auto; }
.volver { display:inline-block; text-decoration:none; color:var(--texto-3); font-size:14px; margin-bottom:22px; }
.volver:hover { color:#fff; }
.nota { color:var(--texto-2); font-size:15px; }

.apoyo { display:flex; align-items:center; gap:20px; flex-wrap:wrap; margin-top:8px; margin-bottom:48px; padding:24px 22px;
  border:1px solid var(--borde); background:var(--tarjeta); border-radius:var(--radio); }
.apoyo div:nth-child(2) { flex:1; min-width:220px; }
.apoyo h2 { font-weight:900; font-size:24px; }
.hist .apoyo { margin-top:44px; margin-bottom:0; }
.apoyo p { color:var(--texto-2); font-size:16px; }
.opiniones { list-style:none; display:flex; flex-direction:column; gap:12px; }
.opiniones li { padding:14px 16px; background:var(--tarjeta); border:1px solid var(--borde); border-radius:var(--radio); }
.opiniones p { font-size:16px; margin:6px 0; }
.opiniones small { color:var(--texto-3); font-size:13px; }
.estrellas { color:var(--oro); letter-spacing:.12em; font-size:16px; }
.formulario { display:block; border:0; min-height:280px; }
footer { border-top:1px solid var(--borde); padding:36px 16px 44px; text-align:center; font-size:14px; color:var(--texto-3); }
footer a { color:var(--texto-2); }
footer small { display:inline-block; margin-top:8px; font-size:12px; }
footer .siguenos { display:block; margin-bottom:12px; font-family:'IBM Plex Mono',monospace; font-size:12px; letter-spacing:.06em; }
footer .siguenos a { color:var(--texto); }
footer .lema { display:block; margin-bottom:12px; font-family:'Playfair Display',serif; font-style:italic; font-size:20px; color:var(--texto); }

/* Misterio: con ratón, la página está en penumbra y una linterna alumbra donde miras (no en las historias, para leer bien) */
.oscuridad { position:fixed; inset:0; z-index:48; pointer-events:none; opacity:0; transition:opacity 1.2s ease;
  background:radial-gradient(circle 300px at var(--cx,50%) var(--cy,40%), transparent 0, rgba(0,0,0,.18) 45%, rgba(0,0,0,.42) 100%); }
.con-linterna .oscuridad { opacity:1; }
body:has(.hist) .oscuridad { display:none; }
/* Ojos que se abren de vez en cuando en la oscuridad de la portada */
.ojos { position:absolute; display:flex; gap:14px; opacity:0; animation:mirada 11s ease-in-out infinite; }
.ojos i { width:12px; height:6px; border-radius:50%; background:#FF3B2E; box-shadow:0 0 12px 3px rgba(255,59,46,.7); animation:parpado 11s steps(1) infinite; }
.ojos.uno { left:72%; top:22%; }
.ojos.dos { left:86%; top:64%; gap:10px; transform:scale(.7); animation-delay:5.5s; }
.ojos.dos i { animation-delay:5.5s; }
@keyframes mirada { 0%,58%,100% { opacity:0; } 62%,80% { opacity:.85; } }
@keyframes parpado { 0%,69% { transform:scaleY(1); } 70% { transform:scaleY(.1); } 72%,100% { transform:scaleY(1); } }
@media (max-width:860px) { .ojos.uno { left:78%; top:8%; } .ojos.dos { display:none; } }

/* Quien pide menos movimiento, lo tiene: sin grano, niebla, parpadeos ni linterna que se mueve */
@media (prefers-reduced-motion:reduce) {
  html { scroll-behavior:auto; }
  body::before, .niebla-fondo::before, .niebla-fondo::after, .portada .sello-grande, .etiqueta-caso::before, .bajar::after { animation:none; }
  .tachado { animation:none; transition:none; }
  .ficha, .ficha .img, .tema, .tema .fondo-img { transition:none; }
  .ficha:hover .img { animation:none; }
  .con-js .aparece { opacity:1; transform:none; transition:none; }
  .ojos, .ojos i { animation:none; opacity:0; } .oscuridad { display:none; }
}
"""

# Temporada de Halloween (del 15 de octubre al 2 de noviembre). web.py solo mete la decoración si genera en esas fechas,
# y el navegador la enciende solo en esas fechas: el 3 de noviembre desaparece sola aunque no se vuelva a publicar.
def es_halloween(d: date | None = None) -> bool:
    d = d or date.today()
    return date(d.year, 10, 15) <= d <= date(d.year, 11, 2)


def telarana_svg() -> str:
    """Telaraña de esquina (la esquina es arriba a la derecha): radios y hilos que cuelgan un poco."""
    cx, cy, angulos = 200, 0, [90 + 15 * i for i in range(7)]
    radios = "".join(f'<line x1="{cx}" y1="{cy}" x2="{cx + 240 * math.cos(math.radians(a)):.1f}" '
                     f'y2="{cy + 240 * math.sin(math.radians(a)):.1f}"/>' for a in angulos)
    hilos = ""
    for r in (28, 58, 92, 130, 172):
        p = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in angulos]
        d = f"M{p[0][0]:.1f},{p[0][1]:.1f}"
        for (x0, y0), (x1, y1) in zip(p, p[1:]):
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            d += f" Q{mx + (cx - mx) * .13:.1f},{my + (cy - my) * .13:.1f} {x1:.1f},{y1:.1f}"
        hilos += f'<path d="{d}"/>'
    return (f'<svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" fill="none" stroke="currentColor" '
            f'stroke-width=".7">{radios}{hilos}</svg>')


ARANA_SVG = """<svg viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg"><g stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round">
<path d="M15 19Q7 12 3 15M14 21Q5 20 2 25M15 24Q8 27 6 33M16 26Q12 32 12 37"/><path d="M25 19Q33 12 37 15M26 21Q35 20 38 25M25 24Q32 27 34 33M24 26Q28 32 28 37"/></g>
<ellipse cx="20" cy="23" rx="6" ry="7.5" fill="currentColor"/><circle cx="20" cy="14.5" r="4" fill="currentColor"/>
<circle cx="18.6" cy="14" r=".9" fill="#E0782F"/><circle cx="21.4" cy="14" r=".9" fill="#E0782F"/></svg>"""

MURCIELAGO_SVG = """<svg viewBox="0 0 64 30" xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" d="M32 9c-1.6-2.6-3.6-3.8-5.6-3.8 1 1.8 1 3 .2 4C22.4 5 15 3.4 8 5.6c3.8 1.8 5.8 4.8 5.8 8.6 3-1.8 6.8-1.8 9 1 1.2-2.8 3.8-3.8 6-2.8.8-2 2-3 3.2-3s2.4 1 3.2 3c2.2-1 4.8 0 6 2.8 2.2-2.8 6-2.8 9-1 0-3.8 2-6.8 5.8-8.6-7-2.2-14.4-.6-18.6 3.6-.8-1-.8-2.2.2-4-2 0-4 1.2-5.6 3.8z"/></svg>"""

# Calabaza con la cara encendida y fantasma, para la portada en Halloween
CALABAZA_SVG = """<svg viewBox="0 0 120 110" xmlns="http://www.w3.org/2000/svg"><path d="M58 14c-2-8 2-13 9-14l2 5c-5 1-6 5-5 9z" fill="#3E4A1E"/>
<ellipse cx="34" cy="62" rx="30" ry="40" fill="#C2561A"/><ellipse cx="86" cy="62" rx="30" ry="40" fill="#C2561A"/><ellipse cx="60" cy="60" rx="34" ry="44" fill="#D9682A"/>
<path d="M60 18v84M36 26c-10 20-10 52 0 74M84 26c10 20 10 52 0 74" stroke="#A9440F" stroke-width="2" fill="none" opacity=".6"/>
<g class="cara"><path d="M34 48l14 4-12 9z M86 48l-14 4 12 9z" fill="#FFD27A"/><path d="M56 62l4-8 4 8z" fill="#FFD27A"/>
<path d="M30 74q30 22 60 0l-6 2-4 7-6-5-6 6-6-6-6 5-4-7z" fill="#FFD27A"/></g></svg>"""
FANTASMA_SVG = """<svg viewBox="0 0 60 70" xmlns="http://www.w3.org/2000/svg"><path d="M30 2C14 2 6 14 6 30v36l8-6 8 6 8-6 8 6 8-6 8 6V30C54 14 46 2 30 2z" fill="#EBDDBF"/>
<ellipse cx="22" cy="28" rx="4" ry="6" fill="#120E0B"/><ellipse cx="38" cy="28" rx="4" ry="6" fill="#120E0B"/><ellipse cx="30" cy="42" rx="5" ry="6" fill="#120E0B"/></svg>"""

HALLOWEEN_CSS = """
/* Halloween: solo con la clase .halloween en <html>, que pone el navegador en temporada */
.cinta-halloween, .deco-halloween { display:none; }
.halloween { --calabaza:#E0782F; }
.halloween .cinta-halloween { display:block; position:relative; z-index:39; text-align:center; font-size:12.5px; line-height:1.5;
  padding:7px 16px; color:#F1CFA6; background:linear-gradient(90deg,#120804,#2B1208 50%,#120804); border-bottom:1px solid rgba(224,120,47,.35); }
.cinta-halloween a { color:var(--calabaza); font-weight:600; text-decoration:none; margin-left:6px; white-space:nowrap; }
.cinta-halloween a:hover { color:#FFB066; }
.vela { display:inline-block; width:6px; height:11px; margin-right:9px; vertical-align:-1px; border-radius:50% 50% 45% 45%;
  background:radial-gradient(circle at 50% 70%,#FFE2A8,#E0782F 65%); box-shadow:0 0 10px 3px rgba(224,120,47,.55);
  animation:llama 1.4s ease-in-out infinite alternate; }
@keyframes llama { 0% { transform:scale(1,1); opacity:1; } 40% { transform:scale(.8,1.15) translateY(-1px); opacity:.8; }
  70% { transform:scale(1.05,.92); opacity:.95; } 100% { transform:scale(.9,1.08); opacity:.85; } }
.halloween header nav a.miedo { color:var(--calabaza); }
.halloween .deco-halloween { display:block; }
/* Telarañas en las esquinas de cada página */
.telarana { position:absolute; z-index:2; pointer-events:none; color:#E8DCC6; opacity:.16; width:min(24vw,230px); }
.telarana svg { display:block; width:100%; height:auto; }
.telarana.der { right:0; top:96px; }
.telarana.izq { left:0; top:96px; transform:scaleX(-1); width:min(15vw,150px); opacity:.11; }
/* Portada: la linterna se vuelve vela, una araña baja por su hilo, niebla y murciélagos */
.halloween .linterna { background:radial-gradient(circle 360px at var(--x,50%) var(--y,40%), rgba(224,120,47,.17), rgba(7,6,6,0) 60%),
  radial-gradient(circle 900px at var(--x,50%) var(--y,40%), transparent 0, rgba(0,0,0,.55) 70%); }
.arana { position:absolute; top:0; right:24%; width:30px; height:150px; z-index:1; pointer-events:none; animation:hilo 9s ease-in-out infinite alternate; }
.arana::before { content:""; position:absolute; left:50%; top:0; bottom:22px; width:1px; background:linear-gradient(rgba(232,220,198,.05),rgba(232,220,198,.4)); }
.arana svg { position:absolute; bottom:0; left:0; width:30px; color:#4A3328; filter:drop-shadow(0 0 2px rgba(255,190,120,.55)) drop-shadow(0 0 10px rgba(224,120,47,.6));
  animation:balanceo 3.2s ease-in-out infinite alternate; transform-origin:50% -120px; }
@keyframes hilo { 0%,15% { height:70px; } 60% { height:230px; } 100% { height:180px; } }
@keyframes balanceo { from { transform:rotate(-4deg); } to { transform:rotate(4deg); } }
.niebla { position:absolute; left:-50vw; right:-50vw; bottom:0; height:45%; z-index:-1; pointer-events:none;
  background:radial-gradient(ellipse 30% 55% at 25% 100%,rgba(210,195,170,.10),transparent 70%),
             radial-gradient(ellipse 28% 45% at 62% 100%,rgba(210,195,170,.08),transparent 70%),
             radial-gradient(ellipse 25% 40% at 85% 100%,rgba(224,120,47,.06),transparent 70%);
  animation:niebla 24s ease-in-out infinite alternate; }
@keyframes niebla { from { transform:translateX(-4%); } to { transform:translateX(4%); } }
.murcielagos { position:absolute; inset:0 -16px; overflow:hidden; z-index:-1; pointer-events:none; }
.murcielago { position:absolute; left:-80px; top:18%; width:38px; color:#1E1410; filter:drop-shadow(0 0 7px rgba(224,120,47,.4));
  animation:vuelo 17s linear infinite; }
.murcielago svg { display:block; width:100%; animation:aleteo .2s ease-in-out infinite alternate; }
.murcielago:nth-child(2) { top:34%; width:26px; animation-duration:21s; animation-delay:6s; }
.murcielago:nth-child(3) { top:9%; width:20px; animation-duration:25s; animation-delay:12s; }
@keyframes vuelo { 0% { transform:translate(0,0); } 25% { transform:translate(30vw,-28px); } 50% { transform:translate(60vw,18px); }
  75% { transform:translate(90vw,-22px); } 100% { transform:translate(calc(100vw + 160px),6px); } }
@keyframes aleteo { from { transform:scaleY(1); } to { transform:scaleY(.35); } }
/* Calabazas encendidas al pie de la portada y un fantasma que cruza de vez en cuando */
.calabaza { position:absolute; bottom:-6px; width:clamp(64px,8vw,110px); z-index:1; pointer-events:none; filter:drop-shadow(0 0 22px rgba(224,120,47,.55)); }
.calabaza svg { display:block; width:100%; height:auto; }
.calabaza.izq { left:-10px; transform:rotate(-6deg); }
.calabaza.der { right:4%; width:clamp(48px,6vw,80px); transform:rotate(5deg); }
.calabaza .cara { animation:vela-calabaza 2.6s ease-in-out infinite alternate; }
@keyframes vela-calabaza { 0% { opacity:1; } 30% { opacity:.7; } 55% { opacity:.95; } 80% { opacity:.6; } 100% { opacity:1; } }
.fantasma { position:absolute; top:30%; left:-90px; width:54px; opacity:0; z-index:0; pointer-events:none; filter:blur(.5px) drop-shadow(0 0 18px rgba(235,221,191,.45));
  animation:fantasma 26s ease-in-out infinite 4s; }
.fantasma svg { display:block; width:100%; }
@keyframes fantasma { 0% { transform:translate(0,0); opacity:0; } 6% { opacity:.22; } 22% { transform:translate(38vw,-40px); opacity:.18; }
  34% { transform:translate(70vw,10px); opacity:0; } 100% { transform:translate(70vw,10px); opacity:0; } }
/* En temporada, los rótulos de sección se vuelven color calabaza */
.halloween .seccion-cab .kicker { color:var(--calabaza); }
.halloween .seccion-cab .kicker::before { content:""; display:inline-block; width:7px; height:7px; margin-right:8px; border-radius:50%; vertical-align:1px;
  background:var(--calabaza); box-shadow:0 0 10px 2px rgba(224,120,47,.6); animation:llama 1.4s ease-in-out infinite alternate; }
.halloween .fila, .halloween .fila-top { scrollbar-color:var(--calabaza) transparent; }
.halloween .etiqueta-caso { color:var(--calabaza); }
.halloween .etiqueta-caso::before { background:var(--calabaza); box-shadow:0 0 16px rgba(224,120,47,.8); }
.halloween .escena .foto-luz { filter:grayscale(.2) sepia(.6) contrast(1.15) brightness(.6) saturate(1.5) hue-rotate(-10deg); }
@media (max-width:1192px) { .niebla { left:-16px; right:-16px; } }
@media (max-width:720px) { .cinta-halloween { font-size:11px; letter-spacing:.08em; } .cinta-halloween .largo { display:none; }
  .telarana.der { width:34vw; top:104px; } .telarana.izq { display:none; } .arana { right:12%; }
  @keyframes hilo { 0%,15% { height:50px; } 60% { height:150px; } 100% { height:120px; } } }
@media (prefers-reduced-motion:reduce) {
  .vela, .arana, .arana svg, .niebla, .calabaza .cara, .halloween .seccion-cab .kicker::before { animation:none; } .murcielagos, .fantasma { display:none; }
}
"""

# Va en <head> para que no haya parpadeo: enciende la temporada solo entre el 15 de octubre y el 2 de noviembre
HALLOWEEN_INICIO = """<script>(function(){var d=new Date(),y=d.getFullYear();if(d>=new Date(y,9,15)&&d<new Date(y,10,3))document.documentElement.classList.add('halloween');})();</script>"""

# Texto de la cinta según el día (cuenta atrás hasta el 31)
HALLOWEEN_CINTA_JS = """<script>(function(){var c=document.getElementById('cinta-texto');if(!c)return;var d=new Date(),y=d.getFullYear();
var hoy=new Date(y,d.getMonth(),d.getDate()),n=Math.round((new Date(y,9,31)-hoy)/864e5),t;
if(n>1)t='Faltan '+n+' noches para Halloween.';else if(n===1)t='Mañana es Halloween. Esta noche, ensayo general.';
else if(n===0)t='Esta noche es Halloween. No leas solo.';else t='Noche de difuntos. Los folios siguen abiertos.';c.textContent=t;})();</script>"""


def cinta_halloween(raiz: str = "") -> str:
    return (f'<div class="cinta-halloween mono" role="note"><span class="vela" aria-hidden="true"></span>'
            f'<span id="cinta-texto">Especial Halloween.</span>'
            f'<a href="{raiz}historias-de-miedo-reales.html">Abre el Top 10<span class="largo"> de historias de miedo reales</span> →</a></div>'
            f'{HALLOWEEN_CINTA_JS}'
            f'<div class="deco-halloween" aria-hidden="true"><div class="telarana der">{telarana_svg()}</div>'
            f'<div class="telarana izq">{telarana_svg()}</div></div>')


def deco_portada() -> str:
    """Araña, niebla y murciélagos para la portada (solo se ven con la clase .halloween)."""
    murcielagos = "".join(f'<div class="murcielago">{MURCIELAGO_SVG}</div>' for _ in range(3))
    return (f'<div class="deco-halloween" aria-hidden="true"><div class="niebla"></div>'
            f'<div class="murcielagos">{murcielagos}</div><div class="arana">{ARANA_SVG}</div>'
            f'<div class="fantasma">{FANTASMA_SVG}</div><div class="calabaza izq">{CALABAZA_SVG}</div>'
            f'<div class="calabaza der">{CALABAZA_SVG}</div></div>')


# Revelar lo tachado, la linterna, la barra de lectura, «Tu archivo» (folios leídos), el test y «Al azar»; en todas las páginas
BASE_JS = """
<script>
(function () {
  var raiz = document.body.dataset.raiz || '';
  var tactil = window.matchMedia('(hover: none)').matches;
  var quieto = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Lo tachado: en móvil, el primer toque revela y el segundo abre el enlace
  document.addEventListener('click', function (ev) {
    var t = ev.target.closest('.tachado');
    var enlace = ev.target.closest('a');
    if (tactil && enlace) {
      var oculto = enlace.querySelector('.tachado:not(.revelado)');
      if (oculto) { ev.preventDefault(); enlace.querySelectorAll('.tachado').forEach(function (x) { x.classList.add('revelado'); }); return; }
    }
    if (t && !enlace) { t.classList.toggle('revelado'); t.setAttribute('aria-pressed', t.classList.contains('revelado')); }
  });
  document.addEventListener('keydown', function (ev) {
    if ((ev.key === 'Enter' || ev.key === ' ') && ev.target.classList && ev.target.classList.contains('tachado')) {
      ev.preventDefault(); ev.target.classList.toggle('revelado'); ev.target.setAttribute('aria-pressed', ev.target.classList.contains('revelado'));
    }
  });

  // Aparecer al hacer scroll: tarjetas, temáticas y bloques entran suavemente
  if ('IntersectionObserver' in window && !quieto) {
    var vigia = new IntersectionObserver(function (entradas) {
      entradas.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add('visto'); vigia.unobserve(en.target); } });
    }, { rootMargin: '0px 0px -8% 0px' });
    document.querySelectorAll('.ficha, .tema, .bloque, .caja, .quiz, .seccion-cab').forEach(function (el) {
      el.classList.add('aparece'); vigia.observe(el);
    });
  }

  // Portada: la linterna sigue al ratón (en móvil deambula sola) y descubre la foto del caso
  var portada = document.querySelector('.portada'), escena = document.querySelector('.escena');
  if (portada && !quieto) {
    var mover = function (x, y) {
      var r = (escena || portada).getBoundingClientRect(), d = escena || portada;
      d.style.setProperty('--x', (x - r.left) + 'px'); d.style.setProperty('--y', (y - r.top) + 'px');
    };
    if (tactil) {
      var t0 = Date.now();
      (function deambular() {
        var s = (Date.now() - t0) / 4000, r = portada.getBoundingClientRect();
        mover(r.left + r.width * (.4 + .3 * Math.sin(s)), r.top + r.height * (.45 + .25 * Math.sin(s * 1.7)));
        requestAnimationFrame(deambular);
      })();
    } else {
      window.addEventListener('pointermove', function (ev) { mover(ev.clientX, ev.clientY); }, { passive: true });
    }
  }

  // Penumbra con linterna: solo con ratón (en táctil no tiene sentido) y si no se pide menos movimiento
  if (!tactil && !quieto && document.querySelector('.oscuridad')) {
    var pendiente = false, cx = 0, cy = 0;
    window.addEventListener('pointermove', function (ev) {
      cx = ev.clientX; cy = ev.clientY;
      if (pendiente) return; pendiente = true;
      requestAnimationFrame(function () {
        var r = document.documentElement; r.style.setProperty('--cx', cx + 'px'); r.style.setProperty('--cy', cy + 'px');
        r.classList.add('con-linterna'); pendiente = false;
      });
    }, { passive: true });
    document.addEventListener('pointerleave', function () { document.documentElement.classList.remove('con-linterna'); });
  }

  // Folio: barra de lectura (cuánto has leído)
  var barra = document.querySelector('.exposicion');
  if (barra) {
    var actualizar = function () {
      var h = document.documentElement, max = h.scrollHeight - h.clientHeight;
      barra.style.width = (max > 0 ? Math.min(100, h.scrollTop / max * 100) : 100) + '%';
    };
    window.addEventListener('scroll', actualizar, { passive: true }); actualizar();
  }

  // Tu archivo: los folios que has abierto se guardan SOLO en este navegador (localStorage), nunca se envían.
  // Si el navegador no deja guardar (modo privado, bloqueo), la web funciona igual, sin contador.
  var leidos = [];
  try { leidos = JSON.parse(localStorage.getItem('folio13-leidos') || '[]'); if (!Array.isArray(leidos)) leidos = []; } catch (e) { leidos = []; }
  var este = document.body.dataset.folio;
  if (este && leidos.indexOf(este) < 0) {
    leidos.push(este);
    try { localStorage.setItem('folio13-leidos', JSON.stringify(leidos)); } catch (e) {}
  }
  var total = parseInt(document.body.dataset.total || '0', 10);
  var n = leidos.length;
  document.querySelectorAll('[data-leidos]').forEach(function (el) {
    if (!total) return;
    var falta = Math.max(0, total - n);
    el.textContent = el.dataset.leidos === 'corto' ? n + ' de ' + total + ' folios leídos'
      : 'Has leído ' + n + ' de ' + total + ' folios' + (falta ? ' · te faltan ' + falta + ' historias por descubrir' : ' · los has leído todos');
  });
  document.querySelectorAll('.progreso .barra i').forEach(function (b) { if (total) b.style.width = Math.min(100, n / total * 100) + '%'; });
  document.querySelectorAll('.ficha[data-folio]').forEach(function (f) { if (leidos.indexOf(f.dataset.folio) >= 0) f.classList.add('leido'); });

  // «¿Lo habrías creído?»: cada dato es verdad (sale del propio folio); se cuenta cuántos te habrías creído
  var quiz = document.querySelector('.quiz');
  if (quiz) {
    var creidos = 0, contestadas = 0, preguntas = quiz.querySelectorAll('.pregunta-bloque');
    preguntas.forEach(function (p) {
      p.querySelectorAll('button').forEach(function (b) {
        b.addEventListener('click', function () {
          p.querySelectorAll('button').forEach(function (x) { x.disabled = true; });
          b.classList.add('elegida');
          if (b.dataset.cree === 'si') creidos++;
          contestadas++;
          p.querySelector('.respuesta').classList.add('vista');
          if (contestadas === preguntas.length) {
            var m = quiz.querySelector('.marcador');
            m.textContent = m.dataset.modo === 'test'
              ? 'Sabías ' + creidos + ' de ' + preguntas.length + '. Las respuestas están en el folio y en sus fuentes.'
              : 'Te habrías creído ' + creidos + ' de ' + preguntas.length + '. Y todas son verdad: por eso están en el folio.';
          }
        });
      });
    });
  }

  // «Al azar»: un folio al azar
  document.querySelectorAll('.sorprendeme').forEach(function (b) {
    b.addEventListener('click', function (ev) {
      ev.preventDefault();
      fetch(raiz + 'indice.json').then(function (r) { return r.json(); }).then(function (lista) {
        var actual = location.pathname.split('/').pop();
        var otros = lista.filter(function (x) { return x.u.split('/').pop() !== actual; });
        var e = otros[Math.floor(Math.random() * otros.length)];
        if (e) location.href = raiz + e.u;
      }).catch(function () { location.href = raiz + 'buscar.html'; });
    });
  });
})();
</script>
"""

# Portada: un secreto distinto en cada visita (las frases van en un JSON dentro de la página)
FRASE_JS = """
<script>
(function () {
  var datos = document.getElementById('frases'), h1 = document.getElementById('frase');
  if (!datos || !h1) return;
  var lista = JSON.parse(datos.textContent);
  if (lista.length < 2) return;
  var p = lista[Math.floor(Math.random() * lista.length)];
  function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
  h1.setAttribute('aria-label', p.antes + p.tachado + p.despues);
  h1.innerHTML = '<a href="' + p.u + '">' + esc(p.antes) + '<span class="tachado">' + esc(p.tachado) + '</span>' + esc(p.despues) + '</a>';
  if (p.img) document.querySelectorAll('.escena .foto, .escena .foto-luz').forEach(function (f) { f.style.backgroundImage = 'url(' + p.img + ')'; });
})();
</script>
"""

FILTRO_JS = """
<script>
// Filtros de las rejillas: cada grupo («tipo»: vídeo o Short; «tema»: la temática) se combina con los demás
(function () {
  var elegido = {};
  document.querySelectorAll('.filtros button').forEach(function (b) {
    b.addEventListener('click', function () {
      var grupo = b.dataset.grupo || 'tipo';
      document.querySelectorAll('.filtros button[data-grupo="' + grupo + '"], .filtros button:not([data-grupo])').forEach(function (x) {
        if ((x.dataset.grupo || 'tipo') === grupo) { x.classList.remove('activo'); x.setAttribute('aria-pressed', 'false'); }
      });
      b.classList.add('activo'); b.setAttribute('aria-pressed', 'true');
      elegido[grupo] = b.dataset.filtro;
      var n = 0;
      document.querySelectorAll('.rejilla .ficha').forEach(function (c) {
        var ve = (!elegido.tipo || elegido.tipo === 'todos' || c.dataset.tipo === elegido.tipo) &&
                 (!elegido.tema || elegido.tema === 'todos' || c.dataset.tema === elegido.tema);
        c.style.display = ve ? '' : 'none'; if (ve) n++;
      });
      var cuenta = document.getElementById('cuenta-folios');
      if (cuenta) cuenta.textContent = n + (n === 1 ? ' folio' : ' folios');
    });
  });
})();
</script>
"""

COPIAR_JS = """
<script>
document.querySelectorAll('.copiar').forEach(function (b) {
  b.addEventListener('click', function () {
    navigator.clipboard.writeText(b.dataset.url).then(function () { b.textContent = '¡Enlace copiado!'; });
  });
});
</script>
"""

BUSCAR_JS = """
<script>
(function () {
  var caja = document.getElementById('q'), sal = document.getElementById('resultados'), cuenta = document.getElementById('cuenta');
  var lista = [];
  function norm(s) { return (s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase(); }
  function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
  function pintar() {
    var q = norm(caja.value).split(/\\s+/).filter(Boolean);
    var res = lista.filter(function (e) {
      var texto = norm([e.t, e.r, (e.e || []).join(' '), e.y, e.l, e.m].join(' '));
      return q.every(function (p) { return texto.indexOf(p) >= 0; });
    });
    cuenta.textContent = q.length ? res.length + (res.length === 1 ? ' folio' : ' folios') : '';
    sal.innerHTML = res.map(function (e) {
      return '<a class="ficha" href="' + e.u + '"><div class="txt"><div class="num mono">' + esc(e.n) + '</div><h3>' + esc(e.t) +
        '</h3><div class="meta">' + esc(e.r) + '</div></div></a>';
    }).join('');
  }
  fetch('indice.json').then(function (r) { return r.json(); }).then(function (d) {
    lista = d; var p = new URLSearchParams(location.search).get('q'); if (p) caja.value = p; pintar();
  });
  caja.addEventListener('input', pintar);
})();
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


# Casos recientes con condenas firmes (Urquijo, Mijas): nada tachado, para que ninguna parte del título se lea como
# una acusación revelada. También vale "censura": false en cualquier expediente.
SIN_TACHAR = {"A025", "A026", "S138", "S139"}


def partes_titulo(e: dict) -> tuple[str, str, str]:
    """Divide el título en (antes, tachado, después). Usa "censura" si existe; si no, tacha el final."""
    titulo = e["titulo"]
    if e.get("censura") is False or e.get("num") in SIN_TACHAR:
        return titulo, "", ""
    censura = (e.get("censura") or "").strip()
    if censura:
        i = titulo.lower().find(censura.lower())
        if i >= 0:
            return titulo[:i], titulo[i:i + len(censura)], titulo[i + len(censura):]
    # Lo que va al final y no se tacha: emojis y un paréntesis final («(1932)», «(la culpa es de una ópera)»)
    m = re.search(r"(\s*\([^()]*\))?(\s*[^\w\s¿?¡!»).,…:]+)?$", titulo)
    cola = m.group(0) if m else ""
    cuerpo = titulo[:len(titulo) - len(cola)] if cola else titulo
    # Si tras los dos puntos, una pregunta o unos puntos suspensivos hay un remate corto, se tacha el remate
    remate = re.search(r"(?:: |\? |… )([^:?…]+\??)$", cuerpo)
    if remate and 1 <= len(remate.group(1).split()) <= 6:
        corte = remate.start(1)
    else:
        palabras = cuerpo.split(" ")
        n = max(2, min(6, round(len(palabras) * 0.4)))
        if len(palabras) <= n:
            return "", cuerpo, cola
        corte = len(" ".join(palabras[:-n])) + 1
    # Que lo tachado no empiece por una palabrita («que», «a», «la»…): queda mejor tachar lo que importa
    resto = cuerpo[corte:].split(" ")
    while len(resto) > 1 and resto[0].lower() in {"a", "al", "de", "del", "el", "la", "las", "los", "en", "y", "que", "un", "una", "su", "se"}:
        corte += len(resto.pop(0)) + 1
    return cuerpo[:corte], cuerpo[corte:], cola


def titulo_html(e: dict, enfocable: bool = False) -> str:
    """Título con la parte tachada. El texto completo sigue en el HTML (lo lee Google y el lector de pantalla)."""
    antes, oculto, despues = partes_titulo(e)
    if not oculto:
        return escape(antes + despues)
    foco = ' tabindex="0" role="button" aria-pressed="false" title="Revelar"' if enfocable else ""
    return f'{escape(antes)}<span class="tachado"{foco}>{escape(oculto)}</span>{escape(despues)}'


TOTAL_FOLIOS = 0   # lo fija generar(): cuántos folios hay, para el contador «Has leído X de N»


def pagina(titulo: str, cuerpo: str, canal: dict, raiz: str = "", descripcion: str = "", extra: str = "",
           ruta: str = "", imagen: str = "compartir.png", tipo_og: str = "website", jsonld=None,
           folio: str = "") -> str:
    texto = (descripcion or canal["lema"]).strip()
    if len(texto) > 158:   # Google corta hacia los 155-160 caracteres: mejor cortar nosotros, en una palabra
        texto = texto[:155].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    desc = escape(texto)
    halloween = es_halloween()
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
           '<meta name="theme-color" content="#12100D">\n'
           f'<link rel="alternate" type="application/rss+xml" title="{escape(canal["nombre"])}" href="{URL}/feed.xml">\n')
    if canal.get("google_verificacion"):
        seo += f'<meta name="google-site-verification" content="{escape(canal["google_verificacion"])}">\n'
    if canal.get("adsense"):   # Google AdSense: el código va en el <head> de todas las páginas
        seo += (f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={escape(canal["adsense"])}" '
                'crossorigin="anonymous"></script>\n')
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
{seo}<link rel="icon" type="image/png" sizes="32x32" href="{raiz}favicon-32.png">
<link rel="apple-touch-icon" href="{raiz}apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700;1,900&family=IBM+Plex+Mono:wght@400;600&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&family=Special+Elite&display=swap">
<style>{CSS}{HALLOWEEN_CSS if halloween else ""}</style>
<script>document.documentElement.classList.add('con-js');</script>
{HALLOWEEN_INICIO if halloween else ""}
</head>
<body data-raiz="{raiz}" data-total="{TOTAL_FOLIOS}"{f' data-folio="{folio}"' if folio else ""}>
<div class="niebla-fondo" aria-hidden="true"></div><div class="oscuridad" aria-hidden="true"></div>
<header><div class="ancho">
  <a class="logo" style="--t:40px" href="{raiz}index.html" aria-label="Inicio">{SELLO_MINI_SVG}</a>
  <a class="nombre" href="{raiz}index.html">Folio <em>13</em></a>
  <nav aria-label="Principal">
    <a href="{raiz}index.html#tematicas">Temáticas</a>
    <a class="solo-ancho" href="{raiz}folios.html">Todos los folios</a>
    <a class="solo-ancho" href="{raiz}mapa.html">Mapa</a>
    <a class="solo-ancho" href="{raiz}acerca.html">Cómo verificamos</a>
    <a class="solo-ancho" href="{raiz}apoya.html">Apoyar</a>
    <a href="{raiz}buscar.html">Buscar</a>
    <a class="sorprendeme" href="{raiz}buscar.html">Al azar</a>
  </nav>
</div></header>
{cinta_halloween(raiz) if halloween else ""}
{cuerpo}
{suscripcion(canal)}
<footer><span class="lema">{escape(canal['lema'])}</span><span class="siguenos">Síguenos: <a href="https://www.instagram.com/elfolio13/" rel="noopener">Instagram</a> · <a href="https://www.tiktok.com/@elfolio13" rel="noopener">TikTok</a> · <a href="{escape(canal['youtube'])}" rel="noopener">YouTube</a> · <a href="https://www.facebook.com/profile.php?id=61596062008062" rel="noopener">Facebook</a> · <a href="{raiz}redes.html">Todas las redes</a></span>© {date.today().year} {MARCA} · <a href="{raiz}index.html#tematicas">Temáticas</a> · <a href="{raiz}mapa.html">Mapa</a> · <a href="{raiz}temas/index.html">Etiquetas</a> · <a href="{raiz}historias-de-miedo-reales.html">Historias de miedo</a> · {f'<a href="{raiz}opiniones.html">Opiniones</a> · ' if canal.get("opiniones_form") else ""}<a href="{raiz}apoya.html">Apoya Folio 13</a> · <a href="{raiz}acerca.html">Cómo verificamos</a> · <a href="{raiz}privacidad.html">Política de privacidad</a> · <a href="{escape(canal['youtube'])}">YouTube</a> · <a href="{URL}/feed.xml">RSS</a>{aviso_afiliados(canal)}</footer>
{BASE_JS}{extra}
</body>
</html>
"""


def apoyo(canal: dict, raiz: str = "") -> str:
    """Bloque de apoyo tras el artículo. Con "donaciones_url" (Ko-fi) sale el botón de donar;
    sin él, solo lleva a la página «Apoya el archivo» (libros), así nunca hay un botón roto."""
    donar = (f'<a class="boton" href="{escape(canal["donaciones_url"])}" rel="noopener" target="_blank">'
             f'{escape((canal.get("donaciones_texto") or "Invítanos a un café").capitalize())} ☕</a>'
             if canal.get("donaciones_url") else "")
    return (f'<section class="apoyo"><div class="logo" style="--t:64px">{sello_svg("-apoyo")}</div>'
            f'<div><h2>¿Abrimos el próximo folio?</h2><p>Cada folio lleva horas de archivo y fuentes. '
            f'Folio 13 es gratis y sin muros de pago: si te ha gustado, puedes ayudarnos a seguir.</p></div>'
            f'<div class="botones" style="margin-top:0">{donar}'
            f'<a class="boton secundario" href="{raiz}apoya.html">Otras formas de apoyar</a></div></section>')


def estrellas(n: int) -> str:
    n = max(1, min(5, int(n or 0)))
    return f'<span class="estrellas" aria-label="{n} de 5">{"★" * n}{"☆" * (5 - n)}</span>'


def lista_opiniones(ops: list[dict], raiz: str = "", con_expediente: bool = False) -> str:
    """Opiniones ya APROBADAS (Web/datos/opiniones.json). Nunca se publica nada sin aprobar."""
    items = ""
    for o in ops:
        sobre = (f' · sobre <a href="{raiz}expedientes/{o["_slug"]}.html">{escape(o["_titulo"])}</a>'
                 if con_expediente and o.get("_slug") else "")
        items += (f'<li>{estrellas(o.get("estrellas", 5))}'
                  + (f'<p>«{escape(o["texto"])}»</p>' if o.get("texto") else "")
                  + f'<small>{escape(o.get("nombre") or "Lector anónimo")} · {fecha_larga(o["fecha"])}{sobre}</small></li>')
    return f'<ul class="opiniones">{items}</ul>' if items else ""


def formulario_opinion(canal: dict, e: dict | None = None) -> str:
    """Formulario de Tally (gratis, sin cuenta para el lector, cumple el RGPD). Las respuestas llegan privadas
    a la cuenta de Tally y solo se publican las que se copian, aprobadas, a datos/opiniones.json."""
    form = canal.get("opiniones_form")
    if not form:
        if SALIDA != WEB:   # solo en la vista previa: hueco visible para ver dónde irá
            return ('<div class="relacionado"><p>[Vista previa] Aquí irá el formulario: estrellas del 1 al 5, opinión '
                    'opcional y nombre opcional. Se activa en cuanto exista el formulario de Tally.</p></div>')
        return ""
    oculto = f"&expediente={urllib.parse.quote(e['_slug'])}" if e else "&expediente=general"
    return (f'<iframe class="formulario" data-tally-src="https://tally.so/embed/{escape(form)}?alignLeft=1&hideTitle=1'
            f'&transparentBackground=1&dynamicHeight=1{oculto}" loading="lazy" width="100%" height="320" frameborder="0" '
            f'title="Deja tu opinión"></iframe>'
            '<script async src="https://tally.so/widgets/embed.js"></script>'
            '<p class="nota" style="margin-top:8px">Las opiniones se revisan antes de publicarse. No pedimos correo ni cuenta.</p>')


def bloque_opiniones(e: dict, canal: dict, ops: list[dict]) -> str:
    formulario = formulario_opinion(canal, e)
    if not formulario and not ops:
        return ""
    return (f'<div class="bloque"><h2>¿Qué te ha parecido este folio?</h2>{formulario}'
            + (f'<h3 style="margin-top:22px">Lo que dicen otros lectores</h3>{lista_opiniones(ops)}' if ops else "")
            + "</div>")


def pagina_opiniones(canal: dict, ops: list[dict]) -> str:
    vacio = ("Todavía no hay opiniones publicadas. ¿Quieres ser la primera persona?" if canal.get("opiniones_form")
             else "Muy pronto podrás dejar aquí tu opinión sobre el archivo.")
    lista = lista_opiniones(ops, con_expediente=True) or f'<p class="nota">{vacio}</p>'
    cuerpo = f"""<main class="ancho seccion lectura">
<h1 style="font-family:'Playfair Display',serif; font-size:clamp(30px,5vw,46px)">Opiniones de los lectores</h1>
<p class="nota" style="margin:10px 0 28px">Lo que opinan quienes han abierto los folios. Todas se revisan antes de publicarse.</p>
{lista}
<div class="bloque"><h2>Deja tu opinión sobre Folio 13</h2>{formulario_opinion(canal)}</div>
</main>"""
    return pagina(f"Opiniones · {canal['nombre']}", cuerpo, canal, ruta="opiniones.html",
                  descripcion="Opiniones de los lectores de Folio 13.")


def pagina_apoya(canal: dict, expedientes: list[dict]) -> str:
    donar = ""
    if canal.get("donaciones_url"):
        donar = (f'<div class="bloque"><h2>Invítanos a un café</h2><p>La forma más directa: un donativo puntual, del '
                 f'importe que quieras, con tarjeta o PayPal.</p><div class="botones">'
                 f'<a class="boton" href="{escape(canal["donaciones_url"])}" rel="noopener" target="_blank">'
                 f'{escape((canal.get("donaciones_texto") or "Invítanos a un café").capitalize())} ☕</a></div></div>')
    libros = ""
    for e in expedientes:
        for l in e.get("lecturas", []):
            libros += enlace_libro(l, canal).replace("</li>", f' <span class="nota">· del folio '
                                                      f'<a href="expedientes/{e["_slug"]}.html">{escape(e["titulo"])}</a></span></li>')
    bloque_libros = (f'<div class="bloque"><h2>Lee los libros de los folios</h2><p>Si compras alguno de estos '
                     f'libros desde aquí, Amazon nos da una pequeña comisión y a ti no te cuesta nada más.</p>'
                     f'<ul class="fuentes">{libros}</ul></div>') if libros else ""
    cuerpo = f"""<main class="ancho seccion lectura">
<h1 style="font-family:'Playfair Display',serif; font-size:clamp(30px,5vw,46px)">Apoya Folio 13</h1>
<p class="bloque" style="margin-top:14px">Folio 13 es gratis, sin muros de pago y sin anuncios invasivos. Detrás de cada folio hay horas buscando fuentes, contrastando cifras y separando el mito de lo que pasó de verdad.</p>
<div class="bloque"><h2>En qué se usa tu ayuda</h2><ul class="curiosidades">
<li>Abrir más folios, con más investigación y mejores fuentes.</li>
<li>Una voz más natural para los vídeos.</li>
<li>Un dominio propio para la web, para que sea más fácil de encontrar y recordar.</li></ul></div>
{donar}
{bloque_libros}
<div class="bloque"><h2>Y gratis</h2><p>Compartir un folio con alguien a quien le vaya a encantar{', <a href="opiniones.html">dejar tu opinión</a>' if canal.get("opiniones_form") else ""} o suscribirte al <a href="{escape(canal['youtube'])}">canal de YouTube</a> también ayuda muchísimo.</p></div>
</main>"""
    return pagina("Apoya Folio 13", cuerpo, canal, ruta="apoya.html",
                  descripcion="Cómo apoyar a Folio 13: donativos, libros recomendados y formas gratuitas.")


def suscripcion(canal: dict) -> str:
    """Invitación a la newsletter; no aparece hasta que haya un enlace en "newsletter_url"."""
    if not canal.get("newsletter_url"):
        return ""
    return (f'<section class="apoyo ancho"><div class="logo" style="--t:56px">{SELLO_MINI_SVG}</div>'
            f'<div><h2>Un folio a la semana, en tu correo</h2><p>Historias reales que parecen inventadas, '
            f'con fuentes. Gratis y sin spam: te das de baja con un clic.</p></div>'
            f'<a class="boton" href="{escape(canal["newsletter_url"])}" rel="noopener">Suscribirme</a></section>')


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


def compartir(e: dict, ruta: str) -> str:
    """Botones para compartir el folio (enlaces normales, sin scripts de terceros)."""
    url = f"{URL}/{ruta}"
    texto = f"{e['titulo']} · {MARCA}"
    q = urllib.parse.quote
    redes = (("WhatsApp", f"https://wa.me/?text={q(texto + ' ' + url)}"),
             ("Telegram", f"https://t.me/share/url?url={q(url)}&text={q(texto)}"),
             ("X", f"https://twitter.com/intent/tweet?url={q(url)}&text={q(texto)}"),
             ("Menéame", f"https://www.meneame.net/submit?url={q(url)}"),
             ("Reddit", f"https://www.reddit.com/submit?url={q(url)}&title={q(e['titulo'])}"))
    botones = "".join(f'<a href="{escape(u)}" rel="noopener" target="_blank">{n}</a>' for n, u in redes)
    return (f'<div class="compartir"><p>¿Conoces a alguien que no se lo creería? Pásale este folio.</p>'
            f'<div>{botones}<button class="copiar" data-url="{escape(url)}">Copiar enlace</button></div></div>')


def num_ficha(e: dict) -> str:
    """«Folio 007 · 1925»: número del folio (por orden de publicación) y época."""
    return " · ".join(x for x in (f"Folio {e['_n']:03d}", e.get("epoca", "")) if x)


SIN_TEMA = {"nombre": "", "corto": "", "intro": ""}   # historia aún sin clasificar (generar() avisa)


def tematica(e: dict) -> dict:
    return TEMATICAS.get(e.get("tematica"), SIN_TEMA)


def semaforo_mini(e: dict) -> str:
    """Las etiquetas del semáforo de la verdad que tenga el folio (sin repetir), para su tarjeta."""
    estados = []
    for v in e.get("verdad", []):
        if v.get("estado") in VERDAD and v["estado"] not in estados:
            estados.append(v["estado"])
    return ('<div class="semaforo">' + "".join(f'<em class="{VERDAD[s][0]}">{VERDAD[s][1].upper()}</em>' for s in estados)
            + "</div>") if estados else ""


def titulo_corto(e: dict) -> str:
    """Título para tarjetas y listas: sin «TOP N HALLOWEEN:» y sin la coletilla de serie («| Cine maldito nº 1»)."""
    return re.sub(r"\s*\|\s*[^|]*$", "", titulo_limpio(e)["titulo"]).strip() or titulo_limpio(e)["titulo"]


def ficha(e: dict, raiz: str = "", con_tema: bool = True) -> str:
    """La ÚNICA forma de pintar una tarjeta (portada, temáticas, etiquetas, «De miedo»…). La foto va entera arriba,
    como <img> con texto alternativo (Google Imágenes) y carga perezosa; el título, limpio, sin tachar.
    Los del Top 10 de Halloween llevan el puesto en grande («Nº 7»)."""
    tipo = "short" if e.get("tipo") == "short" else "video"
    meta = " · ".join(x for x in (e.get("lugar", ""), fecha_larga(e["fecha"])) if x)
    img = e["_img"] if e["_img"].startswith("http") else raiz + e["_img"]
    puesto = puesto_top(e)
    titulo = titulo_corto(e)
    tema = (f'<span class="etiqueta-tema">{escape(tematica(e)["nombre"])}</span>' if con_tema and e["tematica"] else "")
    clase = f' t-{e["tematica"]}" style="--acento:var(--t-acento)' if e["tematica"] else ""
    return (f'<a class="ficha{clase}" data-tipo="{tipo}" data-tema="{e["tematica"]}" data-folio="{e["_n"]}" '
            f'href="{raiz}expedientes/{e["_slug"]}.html">'
            f'<div class="foto"><img class="img" src="{escape(img)}" alt="{escape(titulo)}" loading="lazy" decoding="async">'
            f'<span class="leido-marca">✓ LEÍDO</span><span class="tipo">{"SHORT" if tipo == "short" else "VÍDEO"}</span>'
            + (f'<span class="puesto">Nº {puesto}</span>' if puesto else "") + '</div>'
            f'<div class="txt"><div class="num mono">{escape(num_ficha(e))}</div>{tema}'
            f'<h3>{escape(titulo)}</h3><div class="meta">{escape(meta)}</div>{semaforo_mini(e)}</div></a>')


def donde_cuando(e: dict) -> str:
    """« (Boston, 1919)» para los listados en texto: a una IA le sirve saber dónde y cuándo pasó."""
    partes = [x for x in (e.get("lugar", ""), e.get("epoca", "")) if x]
    return f" ({', '.join(partes)})" if partes else ""


def titulo_limpio(e: dict) -> dict:
    """El folio con el título visible: sin el «TOP N HALLOWEEN:» del principio (la censura se conserva)."""
    if not puesto_top(e):
        return e
    resto = TOP_HALLOWEEN.sub("", e["titulo"])
    limpio = dict(e, titulo=resto[:1].upper() + resto[1:])
    if limpio.get("censura") and limpio["censura"].lower() not in limpio["titulo"].lower():
        limpio.pop("censura")
    return limpio


def anio(e: dict) -> float | None:
    """Año (aproximado) en que pasó, sacado de "epoca": «1888», «hacia 1590-1614», «69-30 a. C.», «Siglos VIII-XI»."""
    epoca = e.get("epoca", "")
    m = re.search(r"\d{1,4}", epoca)
    if m:
        n = int(m.group(0))
        return -n if re.search(r"a\.\s*C", epoca) else n
    romanos = re.search(r"\b([IVXL]+)\b", epoca)
    if romanos:
        valor = {"I": 1, "V": 5, "X": 10, "L": 50}
        r, total = romanos.group(1), 0
        for i, c in enumerate(r):
            total += -valor[c] if i + 1 < len(r) and valor[r[i + 1]] > valor[c] else valor[c]
        return (total - 1) * 100 + 1
    return None


def fuentes_de(expedientes: list[dict]) -> int:
    """Fuentes distintas (por dirección) de una lista de folios."""
    return len({f["url"] for e in expedientes for f in e.get("fuentes", [])})


def temas_de(expedientes: list[dict]) -> dict[str, list[dict]]:
    """Etiqueta → folios, solo las que tienen al menos 2 (una página con 1 aporta poco)."""
    temas: dict[str, list[dict]] = {}
    for e in expedientes:
        for t in e.get("etiquetas", []):
            temas.setdefault(t, []).append(e)
    return {t: es for t, es in sorted(temas.items()) if len(es) >= 2}


def chips_temas(temas: dict[str, list[dict]], raiz: str = "") -> str:
    return ('<div class="chips">' + "".join(
        f'<a href="{raiz}temas/{slug(t)}.html">{escape(t)} <small>{len(es)}</small></a>' for t, es in temas.items())
        + "</div>")


def pagina_tema(tema: str, expedientes: list[dict], canal: dict) -> str:
    """Página de una etiqueta (las de antes, que Google ya conoce). Las temáticas tienen su propia página."""
    ruta = f"temas/{slug(tema)}.html"
    descripcion = (f"{len(expedientes)} folios de Folio 13 sobre {tema.lower()}: "
                   "historias reales que parecen inventadas, con fuentes.")
    cuerpo = f"""<main class="ancho seccion">
<a class="volver" href="index.html">← Todas las etiquetas</a>
<div class="seccion-cab"><h1 style="font-size:clamp(28px,5vw,42px)">{escape(tema)}</h1>
<span class="cuenta">{len(expedientes)} folios</span></div>
<p class="nota" style="margin-bottom:24px">{escape(descripcion)}</p>
<div class="rejilla">{"".join(ficha(e, "../") for e in expedientes)}</div>
</main>"""
    jsonld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": f"Folios: {tema}",
              "url": f"{URL}/{ruta}", "inLanguage": "es", "description": descripcion}
    return pagina(f"{tema}: historias reales con fuentes · {canal['nombre']}", cuerpo, canal, raiz="../",
                  descripcion=descripcion, ruta=ruta, jsonld=jsonld)


# ---------- Temáticas: mapa, línea de tiempo y «si te gusta esto» ----------

TIERRA = WEB / "datos" / "mapa-tierra.txt"   # contorno de los continentes (Natural Earth, dominio público), en 720×360


def mapa_svg(expedientes: list[dict], raiz: str = "", recortar: bool = True) -> str:
    """Mapa con un punto por folio. Se acerca a la zona donde están los casos (sin cortar ninguno)."""
    puntos = [e for e in expedientes if e.get("mapa")]
    if not puntos or not TIERRA.exists():
        return ""
    xs = [(e["mapa"][1] + 180) * 2 for e in puntos]
    ys = [(90 - e["mapa"][0]) * 2 for e in puntos]
    if recortar:
        x0, x1, y0, y1 = min(xs) - 40, max(xs) + 40, min(ys) - 30, max(ys) + 30
        # Proporción 2:1 como mínimo, para que no salga una franja estrecha
        ancho, alto = max(x1 - x0, 120), max(y1 - y0, 60)
        if ancho < alto * 2:
            ancho = alto * 2
        else:
            alto = ancho / 2
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        x0, y0 = max(0, min(720 - ancho, cx - ancho / 2)), max(0, min(360 - alto, cy - alto / 2))
        caja = f"{x0:.0f} {y0:.0f} {min(ancho, 720):.0f} {min(alto, 360):.0f}"
        r = max(2.2, min(ancho, 720) / 110)
    else:
        caja, r = "0 0 720 360", 3.2
    marcas = "".join(
        f'<a href="{raiz}expedientes/{e["_slug"]}.html"><title>{escape(titulo_limpio(e)["titulo"])} · '
        f'{escape(e.get("lugar", ""))}</title><circle class="t-{e["tematica"]}" cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}"/></a>'
        for e, x, y in zip(puntos, xs, ys))
    return (f'<svg class="mapa" viewBox="{caja}" role="img" aria-label="Mapa de los casos">'
            f'<path class="tierra" d="{TIERRA.read_text(encoding="ascii")}"/>{marcas}</svg>')


def linea_tiempo(expedientes: list[dict], raiz: str = "") -> str:
    con_anio = sorted((e for e in expedientes if anio(e) is not None), key=anio)
    if not con_anio:
        return ""
    return ('<ol class="linea">' + "".join(
        f'<li><b>{escape(e.get("epoca", ""))[:14]}</b><a href="{raiz}expedientes/{e["_slug"]}.html">'
        f'{escape(titulo_limpio(e)["titulo"])}</a></li>' for e in con_anio) + "</ol>")


def parecidos(clave: str, todos: list[dict], raiz: str = "") -> str:
    """«Si te gusta esto»: folios de otras temáticas que también tocan esta, o de la temática más parecida."""
    otros = [e for e in todos if e["tematica"] != clave and e.get("tematica_alt") == clave]
    hermana = PARECIDAS[clave]
    otros += [e for e in todos if e["tematica"] == hermana and e not in otros]
    if not otros:
        return ""
    return ('<ul class="parecidos">' + "".join(
        f'<li><small>{escape(tematica(e)["nombre"])}</small><a href="{raiz}expedientes/{e["_slug"]}.html">'
        f'{escape(titulo_limpio(e)["titulo"])}</a></li>' for e in otros[:4]) + "</ul>"
        f'<p style="margin-top:10px; font-size:14px"><a href="{raiz}{hermana}/">Ver {escape(TEMATICAS[hermana]["nombre"].lower())} →</a></p>')


def imagen_de(folios: list[dict], raiz: str = "") -> str:
    """La imagen más reciente de una lista de folios (mejor una miniatura propia que la de YouTube), para fondos."""
    propias = [e for e in folios if not e["_img"].startswith("http") and e["_img"] != "compartir.png"]
    e = (propias or folios or [None])[0]
    if not e:
        return ""
    return e["_img"] if e["_img"].startswith("http") else raiz + e["_img"]


def tarjeta_tematica(clave: str, i: int, folios: list[dict], raiz: str = "") -> str:
    t = TEMATICAS[clave]
    pie = (f"{len(folios)} {'folio' if len(folios) == 1 else 'folios'} · {fuentes_de(folios)} fuentes" if folios
           else "Próximamente · nueva serie")
    img = imagen_de(folios, raiz)
    fondo = f'<div class="fondo-img" style="background-image:url({escape(img)})"></div>' if img else ""
    return (f'<a class="tema t-{clave}" href="{raiz}{clave}/">{fondo}<div><div class="num">TEMÁTICA {i:02d}</div>'
            f'<h3>{escape(t["nombre"])}</h3><p>{escape(t["corto"])}</p></div><div class="pie">{pie}</div></a>')


def pagina_tematica(clave: str, i: int, todas: list[dict], listados: list[dict], canal: dict) -> str:
    """Una temática con su ambiente: todos sus episodios y Shorts, el mapa, la línea de tiempo y «si te gusta esto»."""
    t = TEMATICAS[clave]
    propias = [e for e in todas if e["tematica"] == clave]
    principales = [e for e in propias if not e.get("_episodio")]
    ruta = f"{clave}/"
    descripcion = f"{t['nombre']}: {t['corto']} Historias reales con fuentes, en Folio 13."
    if propias:
        filtros = ('<div class="filtros" role="group" aria-label="Filtrar">'
                   '<button class="activo" data-filtro="todos" aria-pressed="true">Todos</button>'
                   '<button data-filtro="video" aria-pressed="false">Vídeos</button>'
                   '<button data-filtro="short" aria-pressed="false">Shorts</button></div>')
        fichas = (f'<div class="seccion-cab"><h2 style="font-size:24px">{len(principales)} folios'
                  f'{f" y {len(propias) - len(principales)} Shorts de adelanto" if len(propias) > len(principales) else ""}'
                  f'</h2>{filtros}</div><div class="rejilla">{"".join(ficha(e, "../", con_tema=False) for e in propias)}</div>')
        lado = ""
        mapa = mapa_svg(principales, "../")
        if mapa:
            lado += f'<div class="caja"><h2>Mapa de los casos</h2>{mapa}</div>'
        linea = linea_tiempo(principales, "../")
        if linea:
            lado += f'<div class="caja"><h2>Línea de tiempo</h2>{linea}</div>'
    else:
        fichas = (f'<div class="proximamente"><p class="mono" style="font-size:12px">Próximamente</p>'
                  f'<p style="font-size:18px; margin-top:8px">La primera serie de esta temática se está documentando. '
                  f'Mientras tanto, abre otro folio.</p><div class="botones" style="justify-content:center">'
                  f'<a class="boton" href="../index.html#tematicas">Ver todas las temáticas</a></div></div>')
        lado = ""
    mas = parecidos(clave, listados, "../")
    if mas:
        lado += f'<div class="caja"><h2>Si te gusta esto</h2>{mas}</div>'
    img = imagen_de(principales, "../")
    fondo = f'<div class="fondo-img" style="background-image:url({escape(img)})"></div>' if img else ""
    cuerpo = f"""<main class="pagina-tema t-{clave}">
<div class="tema-cab">{fondo}<div class="ancho">
<div class="mono">Temática {i:02d} · {len(principales)} {"folio" if len(principales) == 1 else "folios"}</div>
<h1>{escape(t["nombre"])}</h1>
<p>{escape(t["intro"])}</p>
</div></div>
<div class="ancho tema-cuerpo"><div>{fichas}</div><aside class="lateral">{lado}</aside></div>
</main>"""
    jsonld = [{"@context": "https://schema.org", "@type": "CollectionPage", "name": t["nombre"], "url": f"{URL}/{ruta}",
               "inLanguage": "es", "description": descripcion, "isPartOf": {"@type": "WebSite", "name": MARCA, "url": f"{URL}/"}}]
    if principales:
        jsonld.append({"@context": "https://schema.org", "@type": "ItemList", "name": t["nombre"],
                       "numberOfItems": len(principales),
                       "itemListElement": [{"@type": "ListItem", "position": n, "name": titulo_limpio(e)["titulo"],
                                            "url": f"{URL}/expedientes/{e['_slug']}.html"}
                                           for n, e in enumerate(principales, 1)]})
    return pagina(f"{t['nombre']}: historias reales documentadas · {MARCA}", cuerpo, canal, raiz="../",
                  descripcion=descripcion, ruta=ruta, jsonld=jsonld, extra=FILTRO_JS)


def pagina_folios(listados: list[dict], canal: dict) -> str:
    """Todos los folios en una rejilla, con filtros por formato y por temática."""
    tipos = ('<div class="filtros" role="group" aria-label="Formato">'
             '<button class="activo" data-grupo="tipo" data-filtro="todos" aria-pressed="true">Todo</button>'
             '<button data-grupo="tipo" data-filtro="video" aria-pressed="false">Vídeos</button>'
             '<button data-grupo="tipo" data-filtro="short" aria-pressed="false">Shorts</button></div>')
    temas = ('<div class="filtros" role="group" aria-label="Temática" style="margin-top:10px">'
             '<button class="activo" data-grupo="tema" data-filtro="todos" aria-pressed="true">Todas las temáticas</button>'
             + "".join(f'<button data-grupo="tema" data-filtro="{k}" aria-pressed="false">{escape(t["nombre"])}</button>'
                       for k, t in TEMATICAS.items() if any(e["tematica"] == k for e in listados)) + "</div>")
    descripcion = (f"Los {len(listados)} folios de Folio 13: historias reales de crímenes, leyendas, cine maldito, mitos, "
                   "robos y desastres, todas con sus fuentes.")
    cuerpo = f"""<main class="ancho seccion">
<div class="seccion-cab"><div><span class="kicker">El archivo completo</span><h1 style="font-size:clamp(34px,5vw,54px); line-height:1.05">Todos los folios</h1>
<span class="cuenta" id="cuenta-folios">{len(listados)} folios</span></div></div>
{tipos}{temas}
<div class="rejilla" style="margin-top:22px">{"".join(ficha(e) for e in listados)}</div>
</main>"""
    jsonld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": "Todos los folios", "url": f"{URL}/folios.html",
              "inLanguage": "es", "description": descripcion}
    return pagina(f"Todos los folios: historias reales con fuentes · {MARCA}", cuerpo, canal, ruta="folios.html",
                  descripcion=descripcion, jsonld=jsonld, extra=FILTRO_JS)


def pagina_404(listados: list[dict], canal: dict) -> str:
    """Si alguien llega a una dirección que no existe: en vez de un error, le ofrecemos folios (y no se pierde la visita)."""
    cuerpo = f"""<main class="ancho seccion" style="text-align:center">
<div class="logo" style="--t:120px; margin:20px auto 18px">{sello_svg("-404")}</div>
<h1 style="font-size:clamp(34px,6vw,64px); line-height:1.05">Este folio no existe.</h1>
<p class="nota" style="margin:12px auto 26px; max-width:520px; font-size:18px">O alguien lo hizo desaparecer. Prueba con uno de estos, que sí están documentados.</p>
<div class="botones" style="justify-content:center; margin-bottom:34px"><a class="boton" href="/index.html">Volver al inicio</a>
<a class="boton secundario" href="/buscar.html">Buscar un folio</a></div>
<div class="rejilla" style="text-align:left">{"".join(ficha(e, "/") for e in listados[:4])}</div>
</main>"""
    return pagina(f"Folio no encontrado · {MARCA}", cuerpo, canal, raiz="/", ruta="404.html",
                  descripcion="Esta página no existe. Vuelve a Folio 13 para leer historias reales con fuentes.")


def pagina_redes(canal: dict) -> str:
    """Todas las cuentas de Folio 13 en redes, en una página para enlazar desde las biografías."""
    redes = (("Instagram", "@elfolio13", "https://www.instagram.com/elfolio13/", "Reels y carruseles de cada folio."),
             ("TikTok", "@elfolio13", "https://www.tiktok.com/@elfolio13", "Los Shorts y los vídeos, cada día."),
             ("YouTube", "Folio 13", canal["youtube"], "Los episodios completos."),
             ("Facebook", "Folio 13", "https://www.facebook.com/profile.php?id=61596062008062", "Los folios y los Reels."))
    tarjetas = "".join(f'<a class="tema t-{c}" href="{escape(u)}" rel="noopener"><div><div class="num">{escape(r).upper()}</div>'
                       f'<h3>{escape(h)}</h3><p>{escape(d)}</p></div><div class="pie">Seguir</div></a>'
                       for (r, h, u, d), c in zip(redes, ("crimenes", "paranormal", "cine", "robos")))
    cuerpo = f"""<main class="ancho seccion">
<div class="seccion-cab"><div><span class="kicker">Síguenos</span><h1 style="font-size:clamp(34px,5vw,54px); line-height:1.05">Folio 13 en redes</h1></div></div>
<p class="nota" style="margin-bottom:22px; font-size:18px">Un folio nuevo cada día: historias reales que parecen inventadas, con sus fuentes. Elige dónde verlas.</p>
<div class="rejilla-redes">{tarjetas}</div>
</main>"""
    return pagina(f"Folio 13 en redes: Instagram, TikTok, YouTube y Facebook", cuerpo, canal, ruta="redes.html",
                  descripcion="Sigue a Folio 13 en Instagram, TikTok, YouTube y Facebook: historias reales que parecen inventadas, cada día.")


def pagina_mapa(listados: list[dict], canal: dict) -> str:
    """Todos los folios en el mapa del mundo, con el color de su temática."""
    leyenda = "".join(f'<li class="t-{k}"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;'
                      f'background:var(--t-acento);margin-right:6px"></span><a href="{k}/">{escape(t["nombre"])}</a></li>'
                      for k, t in TEMATICAS.items() if any(e["tematica"] == k for e in listados))
    cuerpo = f"""<main class="ancho seccion">
<div class="seccion-cab"><h1 style="font-size:clamp(28px,5vw,42px)">El mapa de los folios</h1>
<span class="cuenta">{len([e for e in listados if e.get("mapa")])} casos en el mapa</span></div>
<p class="nota" style="margin-bottom:18px">Dónde pasó cada historia. Toca un punto para abrir su folio.</p>
<div class="caja" style="padding:10px">{mapa_svg(listados, recortar=False)}</div>
<ul class="chips" style="list-style:none; margin-top:16px">{leyenda}</ul>
</main>"""
    return pagina(f"Mapa de los folios · {MARCA}", cuerpo, canal, ruta="mapa.html",
                  descripcion="Mapa de todas las historias reales de Folio 13: dónde pasó cada caso.")


# «Historias de miedo reales»: los folios más oscuros (por número o por sus etiquetas)
CASOS_DE_MIEDO = {"A001", "A004", "A009", "A010", "A011"}
PALABRAS_DE_MIEDO = ("miedo", "crimen", "crímenes", "misterio", "leyenda", "críptido", "drácula", "sin resolver",
                     "fantasma", "halloween", "asesin", "terror", "vampir", "monstruo")


def es_de_miedo(e: dict) -> bool:
    texto = " ".join(e.get("etiquetas", []) + [e["titulo"]]).lower()
    return (e.get("num") in CASOS_DE_MIEDO or e.get("tematica") in ("paranormal", "crimenes")
            or any(p in texto for p in PALABRAS_DE_MIEDO))


TOP_HALLOWEEN = re.compile(r"^\s*TOP\s*(\d+)\s*HALLOWEEN\s*:\s*", re.I)


def puesto_top(e: dict) -> int | None:
    """Puesto en el Top 10 de Halloween (del título «TOP 7 HALLOWEEN: …»), o None."""
    m = TOP_HALLOWEEN.match(e["titulo"])
    return int(m.group(1)) if m else None


def bloque_top(expedientes: list[dict], raiz: str = "", enlace: bool = False) -> str:
    """El Top 10 de Halloween como bloque propio, en cuenta atrás (Nº 10 → Nº 1), en una fila que se desliza."""
    top = sorted((e for e in expedientes if puesto_top(e)), key=lambda e: -puesto_top(e))
    if not top:
        return ""
    quedan = 10 - len(top)
    mas = (f' <a href="{raiz}historias-de-miedo-reales.html">Ver todos los casos de miedo →</a>' if enlace else "")
    return (f'<div class="seccion-cab"><h2>Top 10 de Halloween</h2><span class="cuenta">Cuenta atrás: {len(top)} de 10 '
            f'abiertos{f". Los {quedan} restantes, muy pronto" if quedan > 0 else ""}.{mas}</span></div>'
            f'<div class="fila-top">{"".join(ficha(e, raiz) for e in top)}</div>')


def pagina_miedo(expedientes: list[dict], canal: dict) -> str:
    ruta = "historias-de-miedo-reales.html"
    descripcion = ("Historias de miedo reales, documentadas y con fuentes: crímenes antiguos sin resolver, barcos fantasma, "
                   "bestias que aterrorizaron regiones enteras y leyendas que nacieron de hechos reales.")
    # Dos bloques: el Top 10 de Halloween en cuenta atrás (del 10 al 1) y el resto de casos oscuros
    casos = [e for e in expedientes if not puesto_top(e)]
    top = bloque_top(expedientes)
    # En temporada, la página hace de portada de Halloween (título y descripción con la palabra que la gente busca)
    halloween = es_halloween()
    if halloween:
        descripcion = ("Historias de miedo reales para Halloween: el Top 10 en cuenta atrás y más casos "
                       "documentados con fuentes. Crímenes sin resolver, barcos fantasma y bestias que existieron.")
    cuerpo = f"""<main class="ancho seccion">
<div class="sello-txt" style="margin-bottom:22px">{"Especial Halloween" if halloween else "Solo para valientes"}</div>
<h1 style="font-family:'Playfair Display',serif; font-weight:900; font-size:clamp(34px,6vw,64px); line-height:1.08; max-width:18ch">Historias de miedo <span class="tachado" tabindex="0" role="button" aria-pressed="false" title="Revelar">reales</span></h1>
<div class="lectura" style="margin:22px 0 34px; max-width:720px">
<p class="bloque" style="margin-top:0">No hace falta inventar nada para pasar miedo. La historia está llena de sucesos que darían para una película de terror: una granja donde alguien vivió escondido en el desván, un barco que apareció a la deriva sin nadie a bordo, una bestia que atacó durante tres años a los pastores de una región de Francia o un juicio en Galicia contra un hombre que decía convertirse en lobo.</p>
<p class="bloque" style="margin-top:14px">En Folio 13 los contamos como lo que son: casos reales, con sus fuentes, separando lo que se sabe de lo que se añadió después. Sin morbo, pero sin quitarles una pizca de inquietud.</p>
</div>
{top}
<div class="seccion-cab" style="margin-top:56px"><h2>Casos oscuros</h2><span class="cuenta">{len(casos)} {"caso" if len(casos) == 1 else "casos"}. Léelos con la luz encendida.</span></div>
<div class="rejilla">{"".join(ficha(e) for e in casos)}</div>
</main>"""
    jsonld = [{"@context": "https://schema.org", "@type": "CollectionPage", "name": "Historias de miedo reales",
               "url": f"{URL}/{ruta}", "inLanguage": "es", "description": descripcion}]
    lista_top = sorted((e for e in expedientes if puesto_top(e)), key=lambda e: -puesto_top(e))
    if lista_top:   # el Top 10 como lista ordenada, para que los buscadores entiendan la cuenta atrás
        jsonld.append({"@context": "https://schema.org", "@type": "ItemList", "name": "Top 10 de Halloween: historias de miedo reales",
                       "itemListOrder": "https://schema.org/ItemListOrderDescending", "numberOfItems": len(lista_top),
                       "itemListElement": [{"@type": "ListItem", "position": puesto_top(e), "name": titulo_limpio(e)["titulo"],
                                            "url": f"{URL}/expedientes/{e['_slug']}.html"} for e in lista_top]})
    titulo = ("Historias de miedo reales para Halloween: el Top 10 documentado" if halloween
              else "Historias de miedo reales (y documentadas)")
    return pagina(f"{titulo} · {canal['nombre']}", cuerpo, canal, ruta=ruta, descripcion=descripcion, jsonld=jsonld)


def indice_temas(temas: dict[str, list[dict]], canal: dict) -> str:
    descripcion = "Todas las etiquetas de Folio 13: estafas, desastres, mitos, cine, misterios y más."
    cuerpo = f"""<main class="ancho seccion">
<div class="seccion-cab"><h1 style="font-size:clamp(28px,5vw,42px)">Etiquetas</h1>
<span class="cuenta">{len(temas)} etiquetas · <a href="../index.html#tematicas">ver las 7 temáticas</a></span></div>
{chips_temas(temas, "../")}
</main>"""
    return pagina(f"Etiquetas · {canal['nombre']}", cuerpo, canal, raiz="../", descripcion=descripcion,
                  ruta="temas/index.html")


def buscar(canal: dict) -> str:
    cuerpo = """<main class="ancho seccion lectura">
<h1 style="font-size:clamp(28px,5vw,42px)">Buscar un folio</h1>
<label for="q" class="nota" style="display:block; margin-top:14px">Escribe un nombre, un lugar, un año o un tema</label>
<input id="q" class="buscador" type="search" autocomplete="off" placeholder="Ej.: Torre Eiffel, 1919, vampiros…">
<div id="cuenta" class="nota" aria-live="polite" style="margin-bottom:14px"></div>
<div id="resultados" class="rejilla"></div>
</main>"""
    return pagina(f"Buscar · {canal['nombre']}", cuerpo, canal, ruta="buscar.html",
                  descripcion="Busca entre todos los folios de Folio 13.", extra=BUSCAR_JS)


def inicio(canal: dict, expedientes: list[dict]) -> str:
    temas = temas_de(expedientes)
    # Solo las frases cuyo folio ya está publicado; la primera va en el HTML y el navegador elige otra al azar
    por_num = {e["num"]: e for e in expedientes if e.get("num")}
    frases = [dict(p, u=f'expedientes/{por_num[p["num"]]["_slug"]}.html', img=por_num[p["num"]]["_img"])
              for p in (canal.get("portadas") or PORTADAS) if p.get("num") in por_num]
    if not frases:
        frases = [{"antes": "Hay cosas que ", "tachado": "parecen inventadas", "despues": ".", "u": "buscar.html"}]
    p = frases[0]
    frase = (f'<a href="{p["u"]}">{escape(p["antes"])}<span class="tachado">{escape(p["tachado"])}</span>'
             f'{escape(p["despues"])}</a>')
    abrir = (f'<a class="boton" href="expedientes/{expedientes[0]["_slug"]}.html">Abrir el último folio</a>'
             if expedientes else "")
    datos_frases = json.dumps(frases, ensure_ascii=False).replace("</", "<\\/")
    # Portada por filas, como una plataforma: lo último, y luego una fila por temática (cada una lleva a su página)
    ultimos = expedientes[:10]
    fila_ultimos = ('<div class="fila">' + "".join(ficha(e) for e in ultimos)
                    + f'<a class="fila-mas" href="folios.html">Ver los {len(expedientes)} folios →</a></div>') if expedientes else ""
    filas_tema = ""
    for n, clave in enumerate(TEMATICAS, 1):
        propios = [e for e in expedientes if e["tematica"] == clave]
        if not propios:
            continue
        t = TEMATICAS[clave]
        filas_tema += (f'<section class="fila-tema t-{clave}"><div class="seccion-cab"><div><span class="kicker">Temática {n:02d}</span>'
                       f'<h2>{escape(t["nombre"])}</h2></div><a class="ver-todo" href="{clave}/">Ver los {len(propios)} →</a></div>'
                       '<div class="fila">' + "".join(ficha(e, con_tema=False) for e in propios[:10])
                       + (f'<a class="fila-mas" href="{clave}/">Ver todos →</a>' if len(propios) > 10 else "")
                       + "</div></section>")
    tarjetas = "".join(tarjeta_tematica(k, i, [e for e in expedientes if e["tematica"] == k])
                       for i, k in enumerate(TEMATICAS, 1))
    top = bloque_top(expedientes, enlace=True) if es_halloween() else ""
    foto = escape(p.get("img") or imagen_de(expedientes))
    cuerpo = f"""<main class="ancho">
<section class="portada">
  <div class="escena" aria-hidden="true"><div class="foto" style="background-image:url({foto})"></div><div class="foto-luz" style="background-image:url({foto})"></div><div class="ojos uno"><i></i><i></i></div><div class="ojos dos"><i></i><i></i></div></div>
  {deco_portada() if es_halloween() else ""}
  <div class="portada-grid">
  <div>
    <span class="etiqueta-caso">Caso verificado · con fuentes</span>
    <h1 id="frase" aria-label="{escape(p['antes'] + p['tachado'] + p['despues'])}">{frase}</h1>
    <p class="desc">Historias reales que parecen inventadas: crímenes, leyendas, cine maldito y misterios. Cada dato lleva su fuente para que lo compruebes tú.</p>
    <p class="pista">Pasa la linterna por la foto. Toca lo tachado para leerlo.</p>
    <div class="botones" id="abrir">{abrir}<a class="boton secundario sorprendeme" href="buscar.html">Una historia al azar</a></div>
  </div>
  <div class="lateral-portada">
    <div class="logo sello-grande">{sello_svg("-portada")}</div>
    <div class="contador">
      <div><b>{len(expedientes)}</b><span>FOLIOS</span></div>
      <div><b>{fuentes_de(expedientes)}</b><span>FUENTES</span></div>
      <div><b>{len(TEMATICAS)}</b><span>TEMÁTICAS</span></div>
    </div>
    <p class="leidos" data-leidos>{len(expedientes)} historias reales, todas con sus fuentes.</p>
  </div>
  </div>
  <a class="bajar mono" href="#tematicas">Abre el archivo</a>
  <script type="application/json" id="frases">{datos_frases}</script>
</section>
<section class="seccion" style="padding-top:12px; padding-bottom:20px">
  <div class="seccion-cab"><div><span class="kicker">Recién abiertos</span><h2>Lo último del archivo</h2></div><a class="ver-todo" href="folios.html">Ver todos →</a></div>
  {fila_ultimos}
</section>
<section id="tematicas" class="seccion" style="padding-top:20px">
  <div class="seccion-cab"><div><span class="kicker">7 temáticas</span><h2>Elige por dónde empezar</h2></div><span class="cuenta"><a href="mapa.html">Ver todos en el mapa →</a></span></div>
  <div class="rejilla-temas">{tarjetas}</div>
</section>
{f'<section class="seccion bloque-top">{top}</section>' if top else ""}
<section id="folios" class="seccion" style="padding-top:20px">
  <div class="seccion-cab"><div><span class="kicker">Por temática</span><h2>Abre un archivo</h2></div><a class="ver-todo" href="folios.html">Todos los folios →</a></div>
  {filas_tema}
</section>
<section class="seccion" style="padding-top:0">
  <div class="seccion-cab"><div><span class="kicker">Atajos</span><h2>Por etiquetas</h2></div></div>
  {chips_temas(temas)}
</section>
</main>"""
    jsonld = [
        {"@context": "https://schema.org", "@type": "WebSite", "name": MARCA, "alternateName": ANTES, "url": f"{URL}/",
         "inLanguage": "es", "description": canal["descripcion"],
         "potentialAction": {"@type": "SearchAction", "target": f"{URL}/buscar.html?q={{q}}", "query-input": "required name=q"}},
        {"@context": "https://schema.org", "@type": "Organization", "name": MARCA, "alternateName": ANTES, "url": f"{URL}/",
         "slogan": canal["lema"], "logo": f"{URL}/logo.png", "sameAs": [canal["youtube"]] + [u for _, u in REDES_SOCIALES]},
    ]
    return pagina(f"{MARCA} | {canal['lema']} Historias reales con fuentes", cuerpo, canal,
                  descripcion=canal["descripcion"],
                  extra=FRASE_JS, jsonld=jsonld)


NOTA_FUENTE = re.compile(r"\[(\d{1,2})\]")


def parrafo(texto: str, fuentes: list[dict]) -> str:
    """Un párrafo del artículo; «[2]» se vuelve una nota que lleva a la fuente nº 2 (si existe)."""
    partes, ultimo = [], 0
    for m in NOTA_FUENTE.finditer(texto):
        n = int(m.group(1))
        partes.append(escape(texto[ultimo:m.start()]).rstrip())
        ultimo = m.end()
        if 1 <= n <= len(fuentes):   # una nota sin fuente se quita: mejor sin nota que apuntando a otra fuente
            partes.append(f'<sup class="nota-fuente"><a href="#fuente-{n}" title="{escape(fuentes[n - 1]["titulo"])}">{n}</a></sup>')
    partes.append(escape(texto[ultimo:]))
    # Algunos artículos traen negritas de Markdown («**Lo que se discute**»)
    return "<p>" + re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", "".join(partes)) + "</p>"


def lo_que_aprenderas(e: dict) -> list[tuple[str, str]]:
    """3-5 puntos para «Lo que vas a aprender»: los que escribe GUIÓN ("aprender"); si no, los apartados del artículo
    (con su ancla) o, si hay pocos, las curiosidades del folio. Todo sale del propio folio."""
    if len(e.get("aprender", [])) >= 3:
        return [(x, "") for x in e["aprender"][:5]]
    apartados = [(s["titulo"], f"#s{i}") for i, s in enumerate(e.get("articulo", [])) if s.get("titulo")]
    if len(apartados) >= 3:
        return apartados[:5]
    return [(c, "") for c in e.get("curiosidades", [])[:5]] if len(e.get("curiosidades", [])) >= 3 else apartados


def minutos_lectura(e: dict) -> int:
    palabras = len(" ".join([e.get("resumen", "")] + [p for s in e.get("articulo", []) for p in s["parrafos"]]
                            + e.get("curiosidades", [])).split())
    return max(1, round(palabras / 200))


def expediente(e: dict, anterior: dict | None, siguiente: dict | None, canal: dict) -> str:
    tipo = "short" if e.get("tipo") == "short" else "video"
    t = tematica(e)
    fuentes = e.get("fuentes", [])
    datos = "".join(f"<span><b>{k}:</b> {escape(v)}</span>" for k, v in (
        ("Lugar", e.get("lugar", "")), ("Época", e.get("epoca", "")), ("Publicado", fecha_larga(e["fecha"])),
        ("Formato", "Short" if tipo == "short" else "Vídeo")) if v)
    # Lo que vas a aprender
    puntos = lo_que_aprenderas(e)
    aprender = ""
    if puntos:
        items = "".join(f'<li><a href="{a}">{escape(x)}</a></li>' if a else f"<li>{escape(x)}</li>" for x, a in puntos)
        meta = " · ".join([f"{minutos_lectura(e)} min de lectura", "Short" if tipo == "short" else "Vídeo",
                           f"{len(fuentes)} {'fuente' if len(fuentes) == 1 else 'fuentes'}"])
        aprender = (f'<div class="aprender"><h2>Lo que vas a aprender</h2><ol>{items}</ol>'
                    f'<div class="meta mono">{escape(meta)}</div></div>')
    # Artículo completo: lista de secciones {"titulo": "...", "parrafos": ["...", ...]}
    texto = ""
    for i, seccion in enumerate(e.get("articulo", [])):
        titulo = f'<h2>{escape(seccion["titulo"])}</h2>' if seccion.get("titulo") else ""   # la entradilla no lleva título
        texto += (f'<div class="bloque articulo" id="s{i}">{titulo}'
                  + "".join(parrafo(p, fuentes) for p in seccion["parrafos"]) + "</div>")
    # «¿Lo habrías creído?»: las preguntas de GUIÓN ("test") o, si no hay, las tres primeras curiosidades
    curiosidades = e.get("curiosidades", [])
    quiz = ""
    if e.get("test"):
        preguntas = "".join(
            f'<div class="pregunta-bloque"><p class="pregunta"><b>{escape(q["pregunta"])}</b></p><div class="opciones">'
            f'<button type="button" data-cree="si">Lo sé</button><button type="button" data-cree="no">Ni idea</button></div>'
            f'<p class="respuesta">{escape(q["respuesta"])}</p></div>' for q in e["test"][:3])
        quiz = (f'<div class="quiz"><h2>¿Lo habrías creído?</h2><p class="nota">Pon a prueba lo que sabes de este folio.</p>'
                f'{preguntas}<p class="marcador" aria-live="polite" data-modo="test"></p>'
                f'<div class="progreso">TU ARCHIVO <span class="barra"><i></i></span><span data-leidos="corto"></span></div></div>')
    elif curiosidades:
        preguntas = "".join(
            f'<div class="pregunta-bloque"><p class="pregunta">{escape(c)}</p><div class="opciones">'
            f'<button type="button" data-cree="si">Me lo creo</button><button type="button" data-cree="no">No me lo creo</button></div>'
            f'<p class="respuesta">✓ Es verdad. Está en este folio y en sus fuentes.</p></div>' for c in curiosidades[:3])
        quiz = (f'<div class="quiz"><h2>¿Lo habrías creído?</h2><p class="nota">Tres datos de este folio. '
                f'¿Te los habrías creído si te los cuentan sin fuentes?</p>{preguntas}<p class="marcador" aria-live="polite"></p>'
                f'<div class="progreso">TU ARCHIVO <span class="barra"><i></i></span><span data-leidos="corto"></span></div></div>')
    resto = curiosidades if e.get("test") else curiosidades[3:]
    if resto:
        texto += ('<div class="bloque"><h2>Más datos del folio</h2><ul class="curiosidades">'
                  + "".join(f"<li>{escape(c)}</li>" for c in resto) + "</ul></div>")
    lecturas = ""
    if e.get("lecturas"):
        lecturas = ('<div class="bloque"><h2>Para saber más</h2><ul class="fuentes">'
                    + "".join(enlace_libro(l, canal) for l in e["lecturas"]) + "</ul></div>")
    # Columna lateral: semáforo (solo si el folio lo trae), fuentes numeradas y etiquetas
    lado = ""
    if e.get("verdad"):
        filas = "".join(f'<li><em class="{VERDAD[v["estado"]][0]}">{VERDAD[v["estado"]][1].upper()}</em>'
                        f'<span>{parrafo(v["texto"], fuentes)[3:-4]}'
                        + (f' <a href="{escape(v["url"])}" rel="noopener">(fuente)</a>' if v.get("url") else "")
                        + '</span></li>' for v in e["verdad"] if v.get("estado") in VERDAD)
        lado += f'<div class="verdad"><h2>Semáforo de la verdad</h2><ul>{filas}</ul></div>'
    if fuentes:
        lado += ('<div class="fuentes-caja"><h2>Fuentes</h2><ol>'
                 + "".join(f'<li id="fuente-{n}"><a href="{escape(f["url"])}" rel="noopener">{escape(f["titulo"])}</a></li>'
                           for n, f in enumerate(fuentes, 1)) + "</ol></div>")
    if e.get("etiquetas"):
        lado += ('<div class="chips">'
                 + "".join(f'<a href="../temas/{slug(x)}.html">{escape(x)}</a>' for x in e["etiquetas"]) + "</div>")
    nav = '<nav class="navegacion" aria-label="Otros folios">'
    if anterior:
        nav += f'<a href="{anterior["_slug"]}.html"><small>← Folio anterior</small>{escape(anterior["titulo"])}</a>'
    if siguiente:
        nav += f'<a class="sig" href="{siguiente["_slug"]}.html"><small>Folio siguiente →</small>{escape(siguiente["titulo"])}</a>'
    nav += "</nav>"
    if e.get("youtube"):
        video = f"""<div class="reproductor {tipo}"><iframe src="https://www.youtube-nocookie.com/embed/{escape(e['youtube'])}"
  title="{escape(e['titulo'])}" loading="lazy" allowfullscreen
  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"></iframe></div>
<p class="ver-yt"><a href="https://www.youtube.com/watch?v={escape(e['youtube'])}">Ver en YouTube</a></p>"""
    else:
        # Aún no está en YouTube: miniatura y aviso de dónde verlo
        img = e["_img"] if e["_img"].startswith("http") else "../" + e["_img"]
        video = (f'<img src="{escape(img)}" alt="{escape(e["titulo"])}" style="display:block; width:100%; border-radius:8px">'
                 '<p class="ver-yt">El vídeo de este folio ya está en '
                 '<a href="https://www.tiktok.com/@elfolio13" rel="noopener">TikTok</a> y muy pronto llegará a '
                 f'<a href="{escape(canal["youtube"])}">YouTube</a>.</p>')
    if e.get("_episodio"):
        ep = e["_episodio"]
        video += (f'<div class="relacionado"><p>📂 Este Short es un adelanto. El folio completo, con todo el '
                  f'contexto y las fuentes: <a href="{ep["_slug"]}.html">{escape(ep["titulo"])}</a></p></div>')
    # Los Shorts sacados de este episodio no tienen tarjeta propia: van aquí, en «En 1 minuto»
    en_un_minuto = ""
    for s in e.get("_shorts", []):
        reproductor = (f'<div class="reproductor short"><iframe src="https://www.youtube-nocookie.com/embed/{escape(s["youtube"])}"'
                       f' title="{escape(s["titulo"])}" loading="lazy" allowfullscreen'
                       ' allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share">'
                       '</iframe></div>') if s.get("youtube") else ""
        en_un_minuto += (f'<div class="bloque"><h2>En 1 minuto</h2>{reproductor}<p class="ver-yt">'
                         f'<a href="{s["_slug"]}.html">{escape(s["titulo"])}</a>: lo que cuenta este Short, con más detalle</p></div>')
    final = ""
    if siguiente or anterior:
        otro = siguiente or anterior
        final = (f'<div class="sabes-demasiado"><p class="grande">Parecía inventado.</p>'
                 f'<p class="peque">Pero está documentado. Y quedan más folios por abrir.</p>'
                 f'<a class="boton" href="{otro["_slug"]}.html">Abrir el próximo folio</a></div>')
    miga = (f'<div class="miga mono"><a href="../folios.html">{escape(num_ficha(e).split(" · ")[0])}</a>'
            + (f' · <a href="../{e["tematica"]}/">{escape(t["nombre"])}</a>' if e["tematica"] else "")
            + (f' · {escape(e["epoca"])}' if e.get("epoca") else "")
            + (f' · Top 10 de Halloween, nº {puesto_top(e)}' if puesto_top(e) else "") + "</div>")
    img_cab = e["_img"] if e["_img"].startswith("http") else "../" + e["_img"]
    cuerpo = f"""<div class="exposicion" aria-hidden="true"></div>
<main class="hist">
<div class="hist-cab"><div class="fondo-img" style="background-image:url({escape(img_cab)})"></div><div class="ancho">
{miga}
<h1 aria-label="{escape(titulo_limpio(e)['titulo'])}">{titulo_html(titulo_limpio(e), enfocable=True)}</h1>
{f'<p class="sub">{escape(e["resumen"])}</p>' if e.get("resumen") else ""}
<div class="datos">{datos}</div>
</div></div>
<div class="ancho">
<div class="hist-grid">
<div class="hist-texto">
{aprender}
{video}
{texto}
{en_un_minuto}
{quiz}
<div class="relacionado redes-folio"><p>📲 Más folios cada día en <a href="https://www.instagram.com/elfolio13/" rel="noopener">Instagram</a> y <a href="https://www.tiktok.com/@elfolio13" rel="noopener">TikTok</a>: @elfolio13</p></div>
{lecturas}
{apoyo(canal, "../")}
{bloque_opiniones(e, canal, e.get("_opiniones", []))}
{final}
{compartir(e, f"expedientes/{e['_slug']}.html")}
{nav}
</div>
<aside class="hist-lado">{lado}</aside>
</div>
</div></main>"""
    ruta = f"expedientes/{e['_slug']}.html"
    publisher = {"@type": "Organization", "name": MARCA, "alternateName": ANTES, "url": f"{URL}/", "logo": f"{URL}/logo.png"}
    # El artículo va siempre (con sus fuentes como citas): es lo que leen y citan buscadores y asistentes de IA
    articulo = {
        "@context": "https://schema.org", "@type": "Article",
        "headline": titulo_limpio(e)["titulo"][:110], "description": e.get("resumen") or e["titulo"],
        "image": [url_absoluta(e["_img"])], "datePublished": fecha_iso(e["fecha"]),
        "url": f"{URL}/{ruta}", "mainEntityOfPage": f"{URL}/{ruta}", "inLanguage": "es",
        "author": publisher, "publisher": publisher,
        "isPartOf": {"@type": "WebSite", "name": MARCA, "url": f"{URL}/"},
    }
    if t["nombre"]:
        articulo["articleSection"] = t["nombre"]
    if e.get("etiquetas"):
        articulo["keywords"] = ", ".join(e["etiquetas"])
    if fuentes:
        articulo["citation"] = [{"@type": "CreativeWork", "name": f["titulo"], "url": f["url"]} for f in fuentes]
    if e.get("lugar"):
        articulo["contentLocation"] = {"@type": "Place", "name": e["lugar"]}
    if e.get("epoca"):
        articulo["temporalCoverage"] = e["epoca"]
    migas = [{"@type": "ListItem", "position": 1, "name": MARCA, "item": f"{URL}/"}]
    if e["tematica"]:
        migas.append({"@type": "ListItem", "position": 2, "name": t["nombre"], "item": f"{URL}/{e['tematica']}/"})
    migas.append({"@type": "ListItem", "position": len(migas) + 1, "name": titulo_corto(e)})
    jsonld = [articulo, {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": migas}]
    if e.get("youtube"):
        jsonld.append({
            "@context": "https://schema.org", "@type": "VideoObject",
            "name": e["titulo"], "description": e.get("resumen") or e["titulo"],
            "thumbnailUrl": [url_absoluta(e["_img"])], "uploadDate": fecha_iso(e["fecha"]),
            "embedUrl": f"https://www.youtube.com/embed/{e['youtube']}",
            "url": f"{URL}/{ruta}", "inLanguage": "es", "publisher": publisher,
        })
    return pagina(f"{titulo_limpio(e)['titulo']} · {MARCA}", cuerpo, canal, raiz="../", descripcion=e.get("resumen", ""),
                  ruta=ruta, imagen=imagen_compartir(e), tipo_og="video.other" if e.get("youtube") else "article", jsonld=jsonld,
                  extra=COPIAR_JS, folio=str(e["_n"]))


def imagen_compartir(e: dict) -> str:
    """Imagen al compartir el enlace: la tarjeta con el título tachado (og/<slug>.jpg) si ya está hecha."""
    propia = f"og/{e['_slug']}.jpg"
    return propia if (WEB / propia).exists() else e["_img"]


def acerca(canal: dict) -> str:
    redes = "".join(f'<li><a href="{escape(u)}" rel="noopener">{escape(n)}</a></li>' for n, u in (
        ("YouTube · Folio 13", canal["youtube"]), *REDES_SOCIALES))
    cuerpo = f"""<main class="ancho legal">
<a class="volver" href="index.html">← Inicio</a>
<h1>Cómo verificamos</h1>
<div class="fecha">{escape(canal['lema'])}</div>
<h2>Qué es Folio 13</h2>
<p>Folio 13 (antes El Archivo Curioso) es un proyecto de divulgación en español sobre historias reales que cuesta creer: crímenes del pasado, leyendas, cine maldito, mitos, robos y desastres. Cada historia es un «folio»: se publica como vídeo o Short en YouTube y aquí, en la web, con el artículo completo y todas sus fuentes para que puedas comprobarlo. Da escalofrío, pero sin morbo.</p>
<h2>Cómo trabajamos</h2>
<ul>
  <li><b>Fuentes primero.</b> Cada folio se basa en fuentes que citamos en su página: estudios, sentencias, prensa de la época, enciclopedias de referencia, museos y obras de historiadores.</li>
  <li><b>Lo dudoso se dice.</b> Cuando una cifra o una explicación está discutida, lo indicamos en lugar de presentarla como un hecho.</li>
  <li><b>El semáforo de la verdad.</b> Cuando un folio lo incluye, cada dato importante lleva su etiqueta: <i>documentado</i> (lo dicen las fuentes), <i>discutido</i> (las fuentes no se ponen de acuerdo) o <i>leyenda</i> (se cuenta, pero no hay pruebas). Ante la duda, «discutido».</li>
  <li><b>Mitos, desmontados con datos.</b> Si un dato muy repetido no aparece en las fuentes de la época, lo señalamos.</li>
  <li><b>Casos recientes, con cuidado.</b> Solo casos con sentencia firme o cerrados, contando lo que establecen las sentencias y la prensa seria, sin nombres de las víctimas.</li>
  <li><b>Imágenes libres.</b> Usamos obras de dominio público o con licencias libres (sobre todo de Wikimedia Commons) y citamos su origen.</li>
  <li><b>Transparencia.</b> La narración de los vídeos usa una voz sintética, y para preparar los guiones nos ayudamos de herramientas de inteligencia artificial; los datos se contrastan con las fuentes citadas.</li>
</ul>
<h2>¿Has encontrado un error?</h2>
<p>La historia se revisa constantemente. Si crees que un folio contiene un error, escríbenos en los comentarios del vídeo en YouTube o por mensaje privado en redes, con la fuente si la tienes, y lo revisaremos.</p>
<h2>Tu archivo</h2>
<p>La web recuerda qué folios has abierto para enseñarte cuántos te quedan. Esa lista se guarda solo en tu navegador (no se envía a ningún sitio) y se borra al borrar los datos del sitio.</p>
<h2>Dónde encontrarnos</h2>
<ul>{redes}</ul>
</main>"""
    return pagina(f"Cómo verificamos · {MARCA}", cuerpo, canal, ruta="acerca.html",
                  descripcion="Qué es Folio 13, cómo comprobamos cada folio y sus fuentes, y cómo contactar.")


def privacidad(canal: dict) -> str:
    cuerpo = """<main class="ancho legal">
<a class="volver" href="index.html">← Inicio</a>
<h1>Política de privacidad</h1>
<div class="fecha">Última actualización: 28 de octubre de 2026 (publicidad de Google AdSense)</div>
<h2>1. Qué es esta herramienta</h2>
<p>"elarchivocurioso scripts" es una herramienta de uso privado que utiliza la persona responsable del canal de YouTube Folio 13 (antes El Archivo Curioso) para gestionar su propio canal: subir sus vídeos, completar títulos, descripciones, miniaturas, subtítulos y listas de reproducción, y consultar las estadísticas y los comentarios del canal. No es una aplicación pública ni está pensada para que la usen otras personas.</p>
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
<p>Esta web no usa cookies propias. Los vídeos se muestran con el reproductor de YouTube en modo de privacidad mejorada (youtube-nocookie.com); al reproducirlos se aplica la política de privacidad de Google.</p>
<p><b>Publicidad.</b> Esta web muestra anuncios de Google AdSense. Google y sus socios pueden usar cookies para mostrar anuncios según tus visitas a esta y otras webs. En la Unión Europea, te pedimos tu consentimiento antes, con el aviso de privacidad de Google. Puedes desactivar la publicidad personalizada en <a href="https://adssettings.google.com">la configuración de anuncios de Google</a>, y ver cómo usa Google los datos en <a href="https://policies.google.com/technologies/partner-sites">esta página</a>.</p>
<p><b>Tu archivo.</b> La web recuerda en tu propio navegador (localStorage) qué folios has abierto, para el contador «Has leído X de N». No se envía a ningún sitio.</p>
<p><b>Opiniones.</b> El formulario de opiniones es de Tally. Solo se publican las opiniones aprobadas, sin correo.</p>
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
    # Del más reciente al más antiguo; a igual fecha, por número (orden estable)
    visibles.sort(key=lambda e: (e["fecha"], e.get("num") or ""), reverse=True)
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
            for campo in ("articulo", "lecturas", "slug", "censura", "tematica", "tematica_alt", "mapa", "verdad",
                          "aprender", "test"):
                if e.get(campo) and not destino.get(campo):
                    destino[campo] = e[campo]
            visibles.remove(e)
    SALIDA.mkdir(parents=True, exist_ok=True)
    dir_min = SALIDA / "miniaturas"
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
        elif e.get("num") and (WEB / "portadas" / f"{e['num']}.jpg").exists():
            # Portada horizontal limpia de un Short (la hace Promocion/portadas_shorts.py)
            e["_img"] = f"portadas/{e['num']}.jpg"
            if SALIDA != WEB:
                (SALIDA / "portadas").mkdir(exist_ok=True)
                shutil.copyfile(WEB / e["_img"], SALIDA / e["_img"])
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
    # Cada historia debe llevar su temática. Si falta, se usa la de su episodio («de») o su «tematica_alt»; si tampoco
    # hay, sale en la portada y en su página, pero en ninguna temática, y se avisa. Nunca se para la web por esto:
    # la sincronización publica cada día los vídeos que se hacen públicos.
    sin_tema = []
    # Primero los episodios y Shorts sueltos, después los Shorts de un episodio (que heredan la ya resuelta)
    for e in sorted(visibles, key=lambda x: bool(x.get("_episodio"))):
        if e.get("tematica") in TEMATICAS:
            continue
        original = e.get("tematica")
        heredada = (e.get("_episodio") or {}).get("tematica")
        if heredada in TEMATICAS:
            e["tematica"] = heredada
        elif e.get("tematica_alt") in TEMATICAS:
            e["tematica"] = e["tematica_alt"]
        else:
            e["tematica"] = ""
            sin_tema.append(f"  {e.get('num', '?')} · {e['titulo']} ({original or 'sin «tematica»'})")
    if sin_tema:
        print("AVISO: estas historias no tienen una «tematica» válida (" + ", ".join(TEMATICAS) + "). Se publican en la "
              "portada y en su página, pero no en ninguna temática. Añádesela en Web/datos/expedientes.json:\n"
              + "\n".join(sin_tema))
    # Los Shorts que salen de un episodio cuentan lo mismo: tienen página (para YouTube y Google), pero no tarjeta;
    # se ven dentro de su episodio. En las listas solo salen los episodios y los Shorts independientes.
    listados = [e for e in visibles if not e.get("_episodio")]
    # Número de expediente en el archivo: por orden de publicación (el primero es el nº 001)
    for n, e in enumerate(reversed(listados), 1):
        e["_n"] = n
    for e in visibles:
        if e.get("_episodio"):
            e["_n"] = e["_episodio"]["_n"]
    global TOTAL_FOLIOS
    TOTAL_FOLIOS = len(listados)

    # Opiniones aprobadas: Web/datos/opiniones.json, lista de {"expediente": num o slug (o "general"),
    # "estrellas": 1-5, "texto", "nombre", "fecha": "AAAA-MM-DD"}. Lo que no está aquí no se publica.
    ruta_ops = WEB / "datos" / "opiniones.json"
    opiniones = json.loads(ruta_ops.read_text(encoding="utf-8-sig")) if ruta_ops.exists() else []
    por_clave = {k: e for e in visibles for k in (e.get("num"), e["_slug"]) if k}
    for o in opiniones:
        e = por_clave.get(o.get("expediente"))
        e = (e.get("_episodio") or e) if e else None
        if e:
            o["_slug"], o["_titulo"] = e["_slug"], e["titulo"]
            e.setdefault("_opiniones", []).append(o)
    opiniones.sort(key=lambda o: o["fecha"], reverse=True)

    dir_exp = SALIDA / "expedientes"
    if dir_exp.exists():
        shutil.rmtree(dir_exp)
    dir_exp.mkdir()
    for i, e in enumerate(listados):
        anterior = listados[i + 1] if i + 1 < len(listados) else None   # más antiguo
        siguiente = listados[i - 1] if i > 0 else None                  # más reciente
        (dir_exp / f"{e['_slug']}.html").write_text(expediente(e, anterior, siguiente, canal), encoding="utf-8")
    for e in visibles:
        if e.get("_episodio"):
            (dir_exp / f"{e['_slug']}.html").write_text(expediente(e, None, e["_episodio"], canal), encoding="utf-8")

    # Una página por tema (etiqueta) y el índice de temas: más puertas de entrada desde Google
    dir_temas = SALIDA / "temas"
    if dir_temas.exists():
        shutil.rmtree(dir_temas)
    dir_temas.mkdir()
    # Los temas se cuentan con todos los vídeos (así no desaparece ninguna página que Google ya conoce),
    # pero en cada página un Short repetido se cambia por su episodio
    temas = {}
    for tema, es in temas_de(visibles).items():
        unicos = []
        for e in es:
            e = e.get("_episodio") or e
            if e not in unicos:
                unicos.append(e)
        temas[tema] = unicos
    for tema, es in temas.items():
        (dir_temas / f"{slug(tema)}.html").write_text(pagina_tema(tema, es, canal), encoding="utf-8")
    (dir_temas / "index.html").write_text(indice_temas(temas, canal), encoding="utf-8")
    # Las 7 temáticas, cada una en su carpeta (/paranormal/, /crimenes/…), y el mapa de todos los folios
    for i, clave in enumerate(TEMATICAS, 1):
        carpeta = SALIDA / clave
        if carpeta.exists():
            shutil.rmtree(carpeta)
        carpeta.mkdir()
        (carpeta / "index.html").write_text(pagina_tematica(clave, i, visibles, listados, canal), encoding="utf-8")
    (SALIDA / "mapa.html").write_text(pagina_mapa(listados, canal), encoding="utf-8")
    (SALIDA / "folios.html").write_text(pagina_folios(listados, canal), encoding="utf-8")
    (SALIDA / "404.html").write_text(pagina_404(listados, canal), encoding="utf-8")
    (SALIDA / "redes.html").write_text(pagina_redes(canal), encoding="utf-8")

    # Enlace de cada vídeo de YouTube a su página (para ponerlo en las descripciones de YouTube).
    # La sincronización de albuuss depende de este formato: {ID: {num, titulo, url}}
    (SALIDA / "enlaces.json").write_text(json.dumps(
        {e["youtube"]: {"num": e.get("num", ""), "titulo": e["titulo"], "url": f"{URL}/expedientes/{e['_slug']}.html"}
         for e in visibles if e.get("youtube")}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Índice para Buscar y Sorpréndeme (rutas relativas a la raíz)
    # Datos para las imágenes de compartir (las dibuja Promocion/compartir.py; aquí solo el texto)
    (WEB / "datos" / "compartir.json").write_text(json.dumps(
        [dict(zip(("antes", "tachado", "despues"), partes_titulo(e)), slug=e["_slug"], num=num_ficha(e),
              img=e["_img"], tipo=e.get("tipo", "video"), tematica=tematica(e)["nombre"]) for e in visibles],
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (SALIDA / "indice.json").write_text(json.dumps(
        [{"t": titulo_limpio(e)["titulo"], "u": f"expedientes/{e['_slug']}.html", "r": e.get("resumen", ""),
          "e": e.get("etiquetas", []), "y": e.get("epoca", ""), "l": e.get("lugar", ""), "m": tematica(e)["nombre"],
          "n": f"Top 10 de Halloween · Nº {puesto_top(e)}" if puesto_top(e) else num_ficha(e)}
         for e in listados], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    (SALIDA / "index.html").write_text(inicio(canal, listados), encoding="utf-8")
    (SALIDA / "buscar.html").write_text(buscar(canal), encoding="utf-8")
    (SALIDA / "opiniones.html").write_text(pagina_opiniones(canal, opiniones), encoding="utf-8")
    (SALIDA / "apoya.html").write_text(pagina_apoya(canal, listados), encoding="utf-8")
    de_miedo = [e for e in listados if es_de_miedo(e)]
    (SALIDA / "historias-de-miedo-reales.html").write_text(pagina_miedo(de_miedo, canal), encoding="utf-8")
    (SALIDA / "privacidad.html").write_text(privacidad(canal), encoding="utf-8")
    (SALIDA / "acerca.html").write_text(acerca(canal), encoding="utf-8")
    (SALIDA / ".nojekyll").write_text("", encoding="utf-8")
    if LOGO_ORIGEN.exists():
        shutil.copyfile(LOGO_ORIGEN, SALIDA / "logo.png")
    if BANNER_ORIGEN.exists():
        shutil.copyfile(BANNER_ORIGEN, SALIDA / "compartir.png")
    if SALIDA != WEB:
        for icono in ICONOS:
            if (WEB / icono).exists():
                shutil.copyfile(WEB / icono, SALIDA / icono)
    # Dominio propio (GitHub Pages lo lee del archivo CNAME). Sin dominio, no debe existir el archivo
    if DOMINIO:
        (SALIDA / "CNAME").write_text(DOMINIO + "\n", encoding="utf-8")
    elif (SALIDA / "CNAME").exists():
        (SALIDA / "CNAME").unlink()
    # ads.txt de AdSense: dice qué vendedores de anuncios están autorizados a vender en esta web
    if canal.get("adsense"):
        (SALIDA / "ads.txt").write_text(f"google.com, {canal['adsense'].removeprefix('ca-')}, DIRECT, f08c47fec0942fa0\n",
                                        encoding="utf-8")
    # Archivo de verificación de Google Search Console (no se debe borrar nunca)
    if canal.get("google_archivo"):
        (SALIDA / canal["google_archivo"]).write_text(f"google-site-verification: {canal['google_archivo']}",
                                                      encoding="utf-8")

    # Feed RSS: para lectores como Feedly o Inoreader y agregadores de noticias
    items = "".join(
        f"<item><title>{escape_xml(e['titulo'])}</title>"
        f"<link>{URL}/expedientes/{e['_slug']}.html</link>"
        f"<guid>{URL}/expedientes/{e['_slug']}.html</guid>"
        f"<pubDate>{format_datetime(datetime.fromisoformat(e['fecha']).astimezone())}</pubDate>"
        f"<description>{escape_xml(e.get('resumen', ''))}</description></item>"
        for e in visibles)
    (SALIDA / "feed.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        f"<title>{escape_xml(canal['nombre'])}</title><link>{URL}/</link>"
        f"<description>{escape_xml(canal['descripcion'])}</description><language>es</language>"
        f"{items}</channel></rss>\n", encoding="utf-8")

    # Mapa del sitio y robots.txt: así los buscadores encuentran todas las páginas
    hoy = date.today().isoformat()
    entradas = [(f"{URL}/", visibles[0]["fecha"][:10] if visibles else hoy)]
    entradas += [(f"{URL}/expedientes/{e['_slug']}.html", e["fecha"][:10]) for e in visibles]
    entradas += [(f"{URL}/{k}/", max((e["fecha"][:10] for e in visibles if e["tematica"] == k), default=hoy))
                 for k in TEMATICAS]
    entradas.append((f"{URL}/mapa.html", hoy))
    entradas.append((f"{URL}/redes.html", hoy))
    entradas.append((f"{URL}/folios.html", visibles[0]["fecha"][:10] if visibles else hoy))
    entradas += [(f"{URL}/temas/{slug(t)}.html", max(e["fecha"][:10] for e in es)) for t, es in temas.items()]
    entradas.append((f"{URL}/temas/index.html", hoy))
    entradas.append((f"{URL}/apoya.html", hoy))
    entradas.append((f"{URL}/historias-de-miedo-reales.html", hoy))
    if canal.get("opiniones_form"):   # la página de opiniones no se anuncia hasta que exista el formulario
        entradas.append((f"{URL}/opiniones.html", hoy))
    entradas.append((f"{URL}/acerca.html", hoy))
    entradas.append((f"{URL}/privacidad.html", hoy))
    (SALIDA / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{escape_xml(u)}</loc><lastmod>{f}</lastmod></url>\n" for u, f in entradas)
        + "</urlset>\n", encoding="utf-8")
    # Los buscadores de inteligencia artificial (ChatGPT, Perplexity, Claude, Gemini) también pueden leer y citar la web
    robots_ia = "".join(f"User-agent: {b}\nAllow: /\n\n" for b in (
        "OAI-SearchBot", "ChatGPT-User", "GPTBot", "PerplexityBot", "Perplexity-User", "ClaudeBot", "Claude-SearchBot",
        "Claude-User", "Google-Extended", "Bingbot", "Applebot", "Applebot-Extended", "DuckAssistBot",
        "Meta-ExternalAgent", "Amazonbot", "MistralAI-User", "CCBot"))
    (SALIDA / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\n{robots_ia}Sitemap: {URL}/sitemap.xml\n",
                                       encoding="utf-8")
    # llms.txt: resumen del archivo para los asistentes de IA (propuesta llmstxt.org)
    lineas = [f"# {MARCA}", "", f"> {canal['lema']} {canal['descripcion']}", "",
              f"{MARCA} (antes {ANTES}) es una web en español de historias reales que cuesta creer: crímenes del pasado, "
              "leyendas, cine maldito y perdido, mitos desmontados, robos y desastres. Cada historia es un «folio» con "
              "su artículo, sus fuentes enlazadas y su vídeo en YouTube.", "",
              f"- [Historias de miedo reales]({URL}/historias-de-miedo-reales.html): selección de los casos más oscuros.",
              f"- [Mapa de los folios]({URL}/mapa.html): dónde pasó cada historia.",
              "", "## Temáticas", ""]
    lineas += [f"- [{t['nombre']}]({URL}/{k}/): {t['corto']}" for k, t in TEMATICAS.items()]
    lineas += ["", "## Folios", ""]
    lineas += [f"- [{titulo_limpio(e)['titulo']}]({URL}/expedientes/{e['_slug']}.html){donde_cuando(e)}"
               + (f" · {tematica(e)['nombre']}" if e["tematica"] else "") + f": {e.get('resumen', '')}" for e in listados]
    lineas += ["", "## Etiquetas", ""] + [f"- [{t}]({URL}/temas/{slug(t)}.html)" for t in temas]
    lineas += ["", "## Más", "", f"- [Todos los artículos completos, en texto]({URL}/llms-full.txt)",
               f"- [Cómo verificamos cada folio]({URL}/acerca.html)",
               f"- [Canal de YouTube]({canal['youtube']})", ""]
    (SALIDA / "llms.txt").write_text("\n".join(lineas), encoding="utf-8")
    # llms-full.txt: los artículos enteros en texto plano, con sus fuentes, para que una IA pueda leerlos y citarlos
    completo = [f"# {MARCA}: todos los folios", "",
                f"> {canal['lema']} Fuente: {URL}/ · Cada caso enlaza a su página, que es la que conviene citar.", ""]
    for e in listados:
        completo += [f"## {titulo_limpio(e)['titulo']}", "", f"Página: {URL}/expedientes/{e['_slug']}.html"]
        completo += [f"Temática: {tematica(e)['nombre']}"] if e["tematica"] else []
        completo += [f"{k}: {e[c]}" for k, c in (("Lugar", "lugar"), ("Época", "epoca")) if e.get(c)]
        completo += ["", e.get("resumen", ""), ""]
        for seccion in e.get("articulo", []):
            if seccion.get("titulo"):
                completo += [f"### {seccion['titulo']}", ""]
            completo += [p + "\n" for p in seccion["parrafos"]]
        if e.get("curiosidades"):
            completo += ["### Curiosidades", ""] + [f"- {c}" for c in e["curiosidades"]] + [""]
        if e.get("verdad"):
            completo += ["### Semáforo de la verdad", ""] + [f"- {v['estado']}: {v['texto']}" for v in e["verdad"]] + [""]
        if e.get("fuentes"):
            completo += ["### Fuentes", ""] + [f"- [{n}] {f['titulo']}: {f['url']}" for n, f in enumerate(e["fuentes"], 1)] + [""]
    (SALIDA / "llms-full.txt").write_text("\n".join(completo), encoding="utf-8")

    # Clave de IndexNow (Bing, Yandex...): un archivo con la clave en la raíz demuestra que la web es nuestra
    if not CLAVE_INDEXNOW.exists():
        CLAVE_INDEXNOW.write_text(secrets.token_hex(16), encoding="utf-8")
    clave = CLAVE_INDEXNOW.read_text(encoding="utf-8").strip()
    for viejo in SALIDA.glob("*.txt"):
        if re.fullmatch(r"[0-9a-f]{32}\.txt", viejo.name) and viejo.stem != clave:
            viejo.unlink()
    (SALIDA / f"{clave}.txt").write_text(clave, encoding="utf-8")
    ocultos = len(datos["expedientes"]) - len(visibles)
    print(f"Web generada en {SALIDA}: {len(visibles)} expedientes publicados"
          + (f", {ocultos} programados para más adelante" if ocultos else ""))
    return len(visibles)


def git(*args: str) -> subprocess.CompletedProcess:
    exe = shutil.which("git") or r"C:\Program Files\Git\cmd\git.exe"
    return subprocess.run([exe, *args], cwd=WEB, capture_output=True, text=True, encoding="utf-8", errors="replace")


def publicar() -> None:
    if SALIDA != WEB:
        sys.exit("ERROR: WEB_SALIDA es solo para la vista previa; para publicar, quítala.")
    # Antes de generar, se pasan a la web los artículos que GUIÓN haya dejado en Guiones/web/
    importador = WEB.parent / "Promocion" / "importar_articulos.py"
    if importador.exists():
        r = subprocess.run([sys.executable, "-X", "utf8", str(importador)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print(f"AVISO: no se pudieron importar los artículos:\n{r.stderr.strip()}")
    # Portadas horizontales limpias para los Shorts nuevos (Promocion/portadas_shorts.py)
    portadas = WEB.parent / "Promocion" / "portadas_shorts.py"
    if portadas.exists():
        r = subprocess.run([sys.executable, "-X", "utf8", str(portadas)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print(f"AVISO: no se pudieron hacer las portadas de los Shorts:\n{r.stderr.strip()[-500:]}")
    generar()
    # Imágenes para compartir con el título tachado (solo dibuja las nuevas o cambiadas); si hay alguna nueva,
    # se vuelve a generar para que su página la use en og:image
    dibujante = WEB.parent / "Promocion" / "compartir.py"
    if dibujante.exists():
        r = subprocess.run([sys.executable, "-X", "utf8", str(dibujante)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=dibujante.parent)
        if r.returncode != 0:
            print(f"AVISO: no se pudieron dibujar las imágenes para compartir:\n{r.stderr.strip()[-500:]}")
        elif not r.stdout.strip().endswith("0 imagen(es) para compartir dibujadas."):
            generar()
    git("add", "-A")
    if git("status", "--porcelain").stdout.strip():
        r = git("commit", "-m", f"Actualizar web ({date.today().isoformat()})\n\n"
                                  "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>")
        if r.returncode != 0:
            sys.exit(f"ERROR en git commit:\n{r.stderr}")
    # Se sube también si un push anterior falló y quedaron commits sin subir (se reintenta en la siguiente ejecución)
    git("fetch", "-q")
    if git("rev-list", "--count", "@{u}..HEAD").stdout.strip() in ("", "0"):
        print("No hay cambios que subir.")
        return
    # Otras tareas también publican: primero se trae lo suyo, y si el push choca, se reintenta una vez
    for intento in range(2):
        r = git("pull", "--rebase", "-q")
        if r.returncode != 0:
            git("rebase", "--abort")
            sys.exit(f"ERROR en git pull --rebase (hay que revisarlo a mano):\n{r.stderr}")
        r = git("push")
        if r.returncode == 0:
            break
    else:
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
