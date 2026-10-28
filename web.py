"""
web.py - Genera y publica la web de El Archivo Curioso (elarchivocurioso.github.io).

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
Solo usa la biblioteca estándar de Python.
"""

from __future__ import annotations

import json
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
LOGO_ORIGEN = WEB.parent / "Identidad" / "Archivo Curioso" / "icono-512.png"
BANNER_ORIGEN = WEB.parent / "Identidad" / "Archivo Curioso" / "banner.png"
ICONOS = ("favicon-32.png", "apple-touch-icon.png")   # hechos una vez a partir de icono-512.png
URL = "https://elarchivocurioso.github.io"
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

# Logotipo (lupa con «AC»), copiado de Identidad/Archivo Curioso/logo.js. Va en línea para que use Playfair Display
LUPA_SVG = """<svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="El Archivo Curioso">
<line x1="131" y1="131" x2="182" y2="182" stroke="#C8A04A" stroke-width="17" stroke-linecap="round"/>
<line x1="131" y1="131" x2="146" y2="146" stroke="#8C6E30" stroke-width="19"/>
<circle cx="88" cy="88" r="63" fill="#1A1410" stroke="#C8A04A" stroke-width="9"/>
<circle cx="88" cy="88" r="52" fill="none" stroke="#C8A04A" stroke-width="1.6"/>
<text x="88" y="104" text-anchor="middle" font-family="Playfair Display, Georgia, serif" font-weight="700" font-size="50" fill="#EBDDBF" letter-spacing="-1">AC</text>
<line x1="66" y1="118" x2="110" y2="118" stroke="#C2443B" stroke-width="3"/>
</svg>"""

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Playfair+Display:ital,wght@0,700;0,900;1,700;1,900&family=Special+Elite&display=swap');
:root { --fondo:#070606; --tarjeta:#110D0B; --tarjeta-2:#1A1411; --borde:rgba(194,68,59,.14); --borde-2:rgba(232,220,198,.20);
        --texto:#E8DCC6; --texto-2:#A99C86; --texto-3:#6F6558; --oro:#C8A04A; --rojo:#C2443B; --sangre:#8E1B14; }
* { margin:0; padding:0; box-sizing:border-box; }
html { scroll-behavior:smooth; }
body { font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif; background:var(--fondo); color:var(--texto);
  line-height:1.65; min-height:100vh; -webkit-font-smoothing:antialiased; overflow-x:hidden; }
::selection { background:var(--sangre); color:#fff; }
a { color:var(--texto); text-decoration-color:var(--rojo); text-decoration-thickness:1px; text-underline-offset:4px; }
a:hover { color:#fff; }
.ancho { max-width:1160px; margin:0 auto; padding-left:16px; padding-right:16px; }
.mono { font-family:'Special Elite','Courier New',monospace; letter-spacing:.14em; text-transform:uppercase; }
.serif { font-family:'Playfair Display',Georgia,serif; }

/* Atmósfera: grano de película que tiembla y viñeta. No tapan clics. */
body::before { content:""; position:fixed; inset:-50%; z-index:50; pointer-events:none; opacity:.09;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  animation:grano .9s steps(6) infinite; }
body::after { content:""; position:fixed; inset:0; z-index:49; pointer-events:none;
  background:radial-gradient(ellipse at center, transparent 45%, rgba(0,0,0,.72) 100%); }
@keyframes grano { 0%{transform:translate(0,0)} 20%{transform:translate(-3%,2%)} 40%{transform:translate(2%,-3%)}
  60%{transform:translate(-2%,-1%)} 80%{transform:translate(3%,3%)} 100%{transform:translate(0,0)} }

/* Logotipo: lupa con «AC» */
.logo { --t:64px; flex:none; display:block; width:var(--t); height:var(--t); }
.logo svg { display:block; width:100%; height:100%; }

/* Lo censurado: barra negra que se revela al pasar el ratón, al tocar o con el teclado (el texto sigue en el HTML) */
.tachado { color:transparent; padding:0 .03em; cursor:pointer; -webkit-box-decoration-break:clone; box-decoration-break:clone;
  background:repeating-linear-gradient(-45deg,#000 0 6px,#221B17 6px 9px) center / 100% .92em no-repeat; position:relative;
  transition:color .45s ease .1s, background-size .45s cubic-bezier(.6,0,.2,1), text-shadow .45s; animation:interferencia 7s infinite; }
.tachado:hover, .tachado:focus-visible, .tachado.revelado, a:hover .tachado, a:focus-visible .tachado {
  color:#E2503F; background-size:100% 0; text-shadow:0 0 22px rgba(194,68,59,.45); animation:none; }
.tachado:focus-visible { outline:2px solid var(--rojo); outline-offset:3px; }
@keyframes interferencia { 0%,91%,100% { opacity:1; } 92% { opacity:.35; } 93% { opacity:1; } 95% { opacity:.6; } 96% { opacity:1; } }

/* Cabecera */
header { position:sticky; top:0; z-index:40; background:linear-gradient(180deg,rgba(7,6,6,.96),rgba(7,6,6,.75));
  backdrop-filter:blur(8px); -webkit-backdrop-filter:blur(8px); border-bottom:1px solid var(--borde); }
header .ancho { display:flex; align-items:center; gap:12px; height:62px; }
header .nombre { font-family:'Playfair Display',Georgia,serif; font-weight:900; font-size:21px; color:var(--texto); text-decoration:none; line-height:1; white-space:nowrap; }
header .nombre em { color:var(--rojo); }
header nav { margin-left:auto; display:flex; align-items:center; gap:22px; }
header nav a { color:var(--texto-2); text-decoration:none; font-weight:500; font-size:14px; letter-spacing:.02em; }
header nav a:hover { color:var(--texto); }
.sorprendeme { font:600 13px 'Inter',sans-serif; letter-spacing:.04em; color:var(--texto); background:transparent; border:1px solid var(--rojo);
  border-radius:2px; padding:7px 13px; cursor:pointer; text-decoration:none; white-space:nowrap; }
.sorprendeme:hover { background:var(--sangre); color:#fff; }
@media (max-width:720px) { header .ancho { height:56px; } header .nombre { font-size:18px; } header nav { gap:14px; } header nav .solo-ancho { display:none; } }
@media (max-width:420px) { header .nombre { display:none; } }

/* Portada: oscuridad, una linterna que sigue al ratón y una lupa que te mira */
.portada { position:relative; min-height:calc(100svh - 62px); display:flex; flex-direction:column; justify-content:center;
  padding-top:64px; padding-bottom:64px; isolation:isolate; }
.linterna { position:absolute; inset:0 -50vw; z-index:-1; pointer-events:none;
  background:radial-gradient(circle 340px at var(--x,50%) var(--y,40%), rgba(194,68,59,.16), rgba(7,6,6,.0) 60%),
             radial-gradient(circle 900px at var(--x,50%) var(--y,40%), transparent 0, rgba(0,0,0,.55) 70%); }
.portada .susurro { color:var(--texto-3); font-size:13px; margin-bottom:26px; min-height:1.5em; }
.portada .susurro b { color:var(--rojo); font-weight:400; }
.portada h1 { font-family:'Playfair Display',Georgia,serif; font-weight:900; font-size:clamp(32px,5.4vw,70px); line-height:1.14;
  letter-spacing:-.015em; max-width:21ch; }
.portada h1 a { color:inherit; text-decoration:none; }
.sello-rojo { display:inline-block; transform:rotate(-11deg); border:3px double var(--rojo); color:var(--rojo); border-radius:3px;
  padding:4px 14px; font-size:clamp(14px,2vw,19px); letter-spacing:.3em; opacity:.85; mix-blend-mode:screen; }
.portada .sello-rojo { position:absolute; right:4%; top:18%; }
.portada .pista { color:var(--texto-3); font-size:13px; margin-top:18px; }
.portada .desc { color:var(--texto-2); font-size:17px; max-width:560px; margin-top:22px; }
.vigilante { position:absolute; right:6%; bottom:14%; width:min(26vw,240px); opacity:.9; z-index:-1;
  transition:transform .9s cubic-bezier(.2,.7,.2,1); filter:drop-shadow(0 20px 40px rgba(0,0,0,.8)); }
.vigilante svg { width:100%; height:auto; display:block; }
.botones { display:flex; flex-wrap:wrap; gap:12px; margin-top:32px; }
.boton { display:inline-block; font:600 14px 'Inter',sans-serif; letter-spacing:.04em; text-decoration:none; padding:13px 22px; border-radius:2px;
  background:var(--texto); color:#000; border:1px solid var(--texto); cursor:pointer; }
.boton:hover { background:var(--rojo); border-color:var(--rojo); color:#fff; }
.boton.secundario { background:transparent; color:var(--texto); border-color:var(--borde-2); }
.boton.secundario:hover { border-color:var(--rojo); background:var(--sangre); }
.bajar { position:absolute; left:16px; bottom:22px; color:var(--texto-3); font-size:12px; text-decoration:none; }
@media (max-width:720px) { .portada { min-height:auto; padding-top:48px; padding-bottom:56px; }
  .portada .sello-rojo { position:static; margin-bottom:20px; align-self:flex-start; } .vigilante { width:34vw; right:-8%; top:auto; bottom:30%; opacity:.22; } .bajar { display:none; } }

/* Secciones y tarjetas */
.seccion { padding-top:40px; padding-bottom:72px; }
.seccion-cab { display:flex; align-items:flex-end; justify-content:space-between; gap:16px; flex-wrap:wrap; margin-bottom:26px;
  padding-bottom:14px; border-bottom:1px solid var(--borde); }
.seccion-cab h2 { font-family:'Playfair Display',Georgia,serif; font-weight:900; font-size:30px; }
.seccion-cab .cuenta { color:var(--texto-3); font-size:13px; }
.filtros { display:flex; gap:6px; flex-wrap:wrap; }
.filtros button { font:500 13px 'Inter',sans-serif; cursor:pointer; padding:6px 13px; border-radius:2px;
  border:1px solid var(--borde-2); background:transparent; color:var(--texto-2); }
.filtros button.activo { background:var(--texto); color:#000; border-color:var(--texto); }
.rejilla { display:grid; grid-template-columns:repeat(auto-fill,minmax(270px,1fr)); gap:20px; }
.ficha { position:relative; display:flex; flex-direction:column; background:var(--tarjeta); border:1px solid var(--borde); border-radius:3px;
  overflow:hidden; text-decoration:none; color:inherit; transition:transform .3s, border-color .3s, box-shadow .3s; }
.ficha:hover, .ficha:focus-visible { transform:translateY(-4px); border-color:rgba(194,68,59,.5); box-shadow:0 20px 50px -20px rgba(142,27,20,.6); }
.ficha:focus-visible { outline:2px solid var(--rojo); outline-offset:2px; }
.ficha .img { position:relative; aspect-ratio:16/9; background:var(--tarjeta-2) center/cover no-repeat;
  filter:grayscale(1) contrast(1.15) brightness(.6); transition:filter .5s; }
.ficha:hover .img, .ficha:focus-visible .img { filter:grayscale(.2) contrast(1.05) brightness(.95) sepia(.25); }
.ficha .img::after { content:""; position:absolute; inset:0; background:linear-gradient(180deg,transparent 40%,rgba(17,13,11,.95)); }
.ficha .tipo { position:absolute; z-index:1; right:10px; top:10px; padding:2px 8px; font:600 10px 'Inter',sans-serif; letter-spacing:.14em;
  background:rgba(0,0,0,.7); color:var(--texto-2); border:1px solid var(--borde-2); }
.ficha .tipo.short { color:var(--rojo); border-color:rgba(194,68,59,.5); }
.ficha .txt { padding:14px 16px 18px; display:flex; flex-direction:column; gap:8px; }
.ficha .num { color:var(--rojo); font-size:11px; }
.ficha h3 { font-weight:600; font-size:17px; line-height:1.4; }
.ficha .meta { font-size:12px; color:var(--texto-3); }
.vacio { text-align:center; padding:40px 16px 80px; color:var(--texto-2); }
.vacio .logo { --t:80px; margin:0 auto 18px; opacity:.85; }
.chips { display:flex; flex-wrap:wrap; gap:8px; }
.chips a { font-size:13px; color:var(--texto-2); text-decoration:none; padding:6px 12px; border:1px solid var(--borde-2); border-radius:2px; }
.chips a:hover { color:#fff; border-color:var(--rojo); background:var(--sangre); }
.chips a small { color:var(--texto-3); }
.chips a:hover small { color:#fff; }

/* Página de expediente */
.exposicion { position:fixed; left:0; top:0; height:2px; width:0; z-index:60; background:var(--rojo); box-shadow:0 0 12px var(--rojo); }
.reloj { position:fixed; left:16px; bottom:14px; z-index:45; color:var(--texto-3); font-size:11px; pointer-events:none; }
.expediente { padding-top:40px; padding-bottom:80px; }
.lectura { max-width:720px; margin:0 auto; }
.volver { display:inline-block; text-decoration:none; color:var(--texto-3); font-size:13px; margin-bottom:26px; }
.volver:hover { color:var(--texto); }
.expediente .ficha-num { color:var(--rojo); font-size:12px; margin-bottom:14px; }
.expediente h1 { font-family:'Playfair Display',Georgia,serif; font-weight:900; font-size:clamp(32px,5.4vw,52px); line-height:1.08;
  letter-spacing:-.015em; margin-bottom:18px; }
.datos { display:flex; flex-wrap:wrap; gap:6px 18px; margin-bottom:30px; font-size:13px; color:var(--texto-3); }
.datos b { color:var(--texto-2); font-weight:500; }
.reproductor { position:relative; width:100%; aspect-ratio:16/9; overflow:hidden; background:#000; border:1px solid var(--borde); }
.reproductor.short { max-width:360px; aspect-ratio:9/16; margin:0 auto; }
.reproductor iframe { position:absolute; inset:0; width:100%; height:100%; border:0; }
.ver-yt { margin-top:12px; text-align:center; font-size:13px; }
.bloque { margin-top:44px; }
.bloque h2 { font-family:'Playfair Display',Georgia,serif; font-weight:700; font-size:26px; margin-bottom:14px; }
.bloque p { font-size:18px; color:#DDD1BA; }
.articulo p { margin-bottom:18px; }
.articulo p:last-child { margin-bottom:0; }
.bloque.caso p:first-of-type::first-letter { float:left; font-family:'Playfair Display',serif; font-weight:900; font-size:64px; line-height:.9;
  padding:6px 10px 0 0; color:var(--rojo); }
.curiosidades { list-style:none; display:flex; flex-direction:column; gap:10px; counter-reset:c; }
.curiosidades li { position:relative; padding:14px 16px 14px 54px; background:var(--tarjeta); border:1px solid var(--borde); border-radius:2px; font-size:17px; }
.curiosidades li::before { content:counter(c,decimal-leading-zero); counter-increment:c; position:absolute; left:16px; top:15px;
  font-family:'Special Elite',monospace; color:var(--rojo); font-size:15px; }
.fuentes li { margin:6px 0 6px 20px; color:var(--texto-2); }
.nota { color:var(--texto-2); font-size:15px; }
.relacionado { padding:14px 16px; border:1px solid var(--borde); border-left:3px solid var(--rojo); background:var(--tarjeta); }
.relacionado p { font-size:16px; }
.sabes-demasiado { margin-top:64px; padding:40px 20px; text-align:center; border-top:1px solid var(--borde); border-bottom:1px solid var(--borde); }
.sabes-demasiado p.grande { font-family:'Playfair Display',serif; font-style:italic; font-weight:900; font-size:clamp(28px,5vw,40px); color:var(--texto); }
.sabes-demasiado p.peque { color:var(--texto-3); font-size:14px; margin:8px 0 22px; }
.compartir { margin-top:44px; padding:20px 16px; border:1px solid var(--borde); background:var(--tarjeta); text-align:center; }
.compartir p { margin-bottom:12px; color:var(--texto-2); }
.compartir div { display:flex; flex-wrap:wrap; gap:8px; justify-content:center; }
.compartir a, .compartir button { font:500 13px 'Inter',sans-serif; cursor:pointer; padding:7px 13px; border-radius:2px;
  border:1px solid var(--borde-2); background:transparent; color:var(--texto); text-decoration:none; }
.compartir a:hover, .compartir button:hover { border-color:var(--rojo); background:var(--sangre); }
.navegacion { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:44px; }
.navegacion a { display:block; padding:14px 16px; border:1px solid var(--borde); text-decoration:none; color:var(--texto); font-size:15px; }
.navegacion a small { display:block; color:var(--texto-3); font-size:12px; margin-bottom:4px; }
.navegacion a:hover { border-color:var(--rojo); }
.navegacion .sig { text-align:right; grid-column:2; }
@media (max-width:600px) { .navegacion { grid-template-columns:1fr; } .navegacion .sig { grid-column:auto; } .reloj { display:none; } }

/* Buscar */
.buscador { width:100%; font:500 18px 'Inter',sans-serif; padding:14px 18px; border-radius:2px; border:1px solid var(--borde-2);
  background:var(--tarjeta); color:var(--texto); margin:8px 0 22px; }
.buscador:focus { outline:2px solid var(--rojo); outline-offset:1px; }

/* Texto legal y genérico */
.legal { padding-top:40px; padding-bottom:72px; max-width:760px; }
.legal h1 { font-family:'Playfair Display',Georgia,serif; font-weight:900; font-size:clamp(30px,6vw,44px); margin-bottom:6px; }
.legal .fecha { font-size:14px; color:var(--texto-3); margin-bottom:24px; }
.legal h2 { color:var(--rojo); font-weight:600; font-size:19px; margin:28px 0 8px; }
.legal p, .legal li { font-size:16px; color:#DDD1BA; }
.legal ul { padding-left:22px; }

.apoyo { display:flex; align-items:center; gap:22px; flex-wrap:wrap; margin-top:8px; margin-bottom:48px; padding:24px 20px;
  border:1px solid var(--borde); background:var(--tarjeta); }
.apoyo div:nth-child(2) { flex:1; min-width:220px; }
.apoyo h2 { font-family:'Playfair Display',serif; font-weight:900; font-size:22px; }
.apoyo p { color:var(--texto-2); font-size:15px; }
footer { border-top:1px solid var(--borde); padding:28px 16px 40px; text-align:center; font-size:13px; color:var(--texto-3); }
footer a { color:var(--texto-2); }
footer small { display:inline-block; margin-top:8px; font-size:12px; }
footer .ultima { display:block; margin-bottom:10px; font-family:'Special Elite',monospace; letter-spacing:.14em; text-transform:uppercase; font-size:11px; color:var(--texto-3); }

/* Quien pide menos movimiento, lo tiene: sin grano animado, sin interferencias ni linterna que se mueve */
@media (prefers-reduced-motion:reduce) {
  html { scroll-behavior:auto; }
  body::before { animation:none; }
  .tachado { animation:none; transition:none; }
  .vigilante, .ficha, .ficha .img { transition:none; }
}
"""

# Revelar lo tachado, la linterna y la lupa que mira, el reloj del expediente y «Sorpréndeme»; en todas las páginas
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

  // Portada: la linterna sigue al ratón (en móvil deambula sola) y la lupa se gira hacia ti
  var portada = document.querySelector('.portada'), vigilante = document.querySelector('.vigilante');
  if (portada && !quieto) {
    var mover = function (x, y) {
      var r = portada.getBoundingClientRect();
      portada.style.setProperty('--x', (x - r.left) + 'px'); portada.style.setProperty('--y', (y - r.top) + 'px');
      if (vigilante) {
        var v = vigilante.getBoundingClientRect(), cx = v.left + v.width / 2, cy = v.top + v.height / 2;
        var dx = Math.max(-30, Math.min(30, (x - cx) / 18)), dy = Math.max(-30, Math.min(30, (y - cy) / 18));
        vigilante.style.transform = 'translate(' + dx + 'px,' + dy + 'px) rotate(' + (dx / 3) + 'deg)';
      }
    };
    if (tactil) {
      var t0 = Date.now();
      (function deambular() {
        var s = (Date.now() - t0) / 4000, r = portada.getBoundingClientRect();
        mover(r.left + r.width * (.5 + .35 * Math.sin(s)), r.top + r.height * (.45 + .25 * Math.sin(s * 1.7)));
        requestAnimationFrame(deambular);
      })();
    } else {
      window.addEventListener('pointermove', function (ev) { mover(ev.clientX, ev.clientY); }, { passive: true });
    }
  }

  // Hora a la que abriste el archivo (solo se muestra aquí; no se guarda ni se envía a ningún sitio)
  var hora = document.querySelector('[data-hora]');
  if (hora) { var d = new Date(); hora.textContent = d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }); }

  // Expediente: barra de exposición (cuánto has leído) y tiempo que llevas dentro
  var barra = document.querySelector('.exposicion'), reloj = document.querySelector('.reloj');
  if (barra) {
    var actualizar = function () {
      var h = document.documentElement, max = h.scrollHeight - h.clientHeight;
      barra.style.width = (max > 0 ? Math.min(100, h.scrollTop / max * 100) : 100) + '%';
    };
    window.addEventListener('scroll', actualizar, { passive: true }); actualizar();
  }
  if (reloj) {
    var inicio = Date.now();
    setInterval(function () {
      var s = Math.floor((Date.now() - inicio) / 1000);
      reloj.textContent = 'Llevas ' + String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0') + ' dentro de este expediente';
    }, 1000);
  }

  // «Sorpréndeme»: un expediente al azar
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
  var abrir = document.querySelector('#abrir .boton:not(.sorprendeme)');
  if (abrir) abrir.href = p.u;
})();
</script>
"""

FILTRO_JS = """
<script>
document.querySelectorAll('.filtros button').forEach(function (b) {
  b.addEventListener('click', function () {
    document.querySelectorAll('.filtros button').forEach(function (x) { x.classList.remove('activo'); x.setAttribute('aria-pressed', 'false'); });
    b.classList.add('activo'); b.setAttribute('aria-pressed', 'true');
    var f = b.dataset.filtro;
    document.querySelectorAll('.rejilla .ficha').forEach(function (c) {
      c.style.display = (f === 'todos' || c.dataset.tipo === f) ? '' : 'none';
    });
  });
});
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
      var texto = norm([e.t, e.r, (e.e || []).join(' '), e.y, e.l].join(' '));
      return q.every(function (p) { return texto.indexOf(p) >= 0; });
    });
    cuenta.textContent = q.length ? res.length + (res.length === 1 ? ' expediente' : ' expedientes') : '';
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


def partes_titulo(e: dict) -> tuple[str, str, str]:
    """Divide el título en (antes, tachado, después). Usa "censura" si existe; si no, tacha el final."""
    titulo = e["titulo"]
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
    foco = ' tabindex="0" role="button" aria-pressed="false" title="Revelar"' if enfocable else ""
    return f'{escape(antes)}<span class="tachado"{foco}>{escape(oculto)}</span>{escape(despues)}'


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
           '<meta name="theme-color" content="#0F0C0A">\n'
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
{seo}<link rel="icon" type="image/png" sizes="32x32" href="{raiz}favicon-32.png">
<link rel="apple-touch-icon" href="{raiz}apple-touch-icon.png">
<style>{CSS}</style>
</head>
<body data-raiz="{raiz}">
<header><div class="ancho">
  <a class="logo" style="--t:40px" href="{raiz}index.html" aria-label="Inicio">{LUPA_SVG}</a>
  <a class="nombre" href="{raiz}index.html">El Archivo <em>Curioso</em></a>
  <nav aria-label="Principal">
    <a href="{raiz}index.html#expedientes">Expedientes</a>
    <a class="solo-ancho" href="{raiz}temas/index.html">Temas</a>
    <a href="{raiz}buscar.html">Buscar</a>
    <a class="sorprendeme" href="{raiz}buscar.html">Sorpréndeme</a>
  </nav>
</div></header>
{cuerpo}
{suscripcion(canal)}
{apoyo(canal)}
<footer>© {date.today().year} {escape(canal['nombre'])} · <a href="{raiz}temas/index.html">Temas</a> · <a href="{raiz}acerca.html">Acerca del archivo</a> · <a href="{raiz}privacidad.html">Política de privacidad</a> · <a href="{escape(canal['youtube'])}">YouTube</a> · <a href="{URL}/feed.xml">RSS</a>{aviso_afiliados(canal)}</footer>
{BASE_JS}{extra}
</body>
</html>
"""


def apoyo(canal: dict) -> str:
    """Bloque de donaciones; no aparece hasta que haya un enlace en "donaciones_url"."""
    if not canal.get("donaciones_url"):
        return ""
    return (f'<section class="apoyo ancho"><div class="logo" style="--t:56px">{LUPA_SVG}</div>'
            f'<div><h2>¿Te gusta El Archivo Curioso?</h2><p>Cada expediente lleva horas de investigación. '
            f'Si quieres ayudar a abrir el siguiente, puedes invitarnos a un café.</p></div>'
            f'<a class="boton" href="{escape(canal["donaciones_url"])}" rel="noopener">'
            f'{escape(canal.get("donaciones_texto") or "Invítanos a un café")}</a></section>')


def suscripcion(canal: dict) -> str:
    """Invitación a la newsletter; no aparece hasta que haya un enlace en "newsletter_url"."""
    if not canal.get("newsletter_url"):
        return ""
    return (f'<section class="apoyo ancho"><div class="logo" style="--t:56px">{LUPA_SVG}</div>'
            f'<div><h2>Un expediente a la semana, en tu correo</h2><p>Historias reales que parecen inventadas, '
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
    """Botones para compartir el expediente (enlaces normales, sin scripts de terceros)."""
    url = f"{URL}/{ruta}"
    texto = f"{e['titulo']} · El Archivo Curioso"
    q = urllib.parse.quote
    redes = (("WhatsApp", f"https://wa.me/?text={q(texto + ' ' + url)}"),
             ("Telegram", f"https://t.me/share/url?url={q(url)}&text={q(texto)}"),
             ("X", f"https://twitter.com/intent/tweet?url={q(url)}&text={q(texto)}"),
             ("Menéame", f"https://www.meneame.net/submit?url={q(url)}"),
             ("Reddit", f"https://www.reddit.com/submit?url={q(url)}&title={q(e['titulo'])}"))
    botones = "".join(f'<a href="{escape(u)}" rel="noopener" target="_blank">{n}</a>' for n, u in redes)
    return (f'<div class="compartir"><p>¿Conoces a alguien a quien le encantaría este expediente? Pásaselo.</p>'
            f'<div>{botones}<button class="copiar" data-url="{escape(url)}">Copiar enlace</button></div></div>')


def num_ficha(e: dict) -> str:
    """«Nº 007 · 1925»: número del expediente en el archivo y época."""
    return " · ".join(x for x in (f"Nº {e['_n']:03d}", e.get("epoca", "")) if x)


def ficha(e: dict, raiz: str = "") -> str:
    tipo = "short" if e.get("tipo") == "short" else "video"
    meta = " · ".join(x for x in (e.get("lugar", ""), fecha_larga(e["fecha"])) if x)
    img = e["_img"] if e["_img"].startswith("http") else raiz + e["_img"]
    return (f'<a class="ficha" data-tipo="{tipo}" href="{raiz}expedientes/{e["_slug"]}.html">'
            f'<div class="img" style="background-image:url({escape(img)})">'
            f'<span class="tipo {tipo}">{"SHORT" if tipo == "short" else "VÍDEO"}</span></div>'
            f'<div class="txt"><div class="num mono">{escape(num_ficha(e))}</div>'
            f'<h3 aria-label="{escape(e["titulo"])}">{titulo_html(e)}</h3><div class="meta">{escape(meta)}</div></div></a>')


def temas_de(expedientes: list[dict]) -> dict[str, list[dict]]:
    """Etiqueta → expedientes, solo las que tienen al menos 2 (una página con 1 aporta poco)."""
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
    ruta = f"temas/{slug(tema)}.html"
    descripcion = (f"{len(expedientes)} expedientes de El Archivo Curioso sobre {tema.lower()}: "
                   "historias reales que parecen inventadas, con fuentes.")
    cuerpo = f"""<main class="ancho seccion">
<a class="volver" href="index.html">← Todos los temas</a>
<div class="seccion-cab"><h1 class="expediente-titulo" style="font-size:clamp(28px,5vw,42px); letter-spacing:-.02em">{escape(tema)}</h1>
<span class="cuenta">{len(expedientes)} expedientes</span></div>
<p class="nota" style="margin-bottom:24px">{escape(descripcion)}</p>
<div class="rejilla">{"".join(ficha(e, "../") for e in expedientes)}</div>
</main>"""
    jsonld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": f"Expedientes: {tema}",
              "url": f"{URL}/{ruta}", "inLanguage": "es", "description": descripcion}
    return pagina(f"{tema}: historias y curiosidades · {canal['nombre']}", cuerpo, canal, raiz="../",
                  descripcion=descripcion, ruta=ruta, jsonld=jsonld)


def indice_temas(temas: dict[str, list[dict]], canal: dict) -> str:
    descripcion = "Todos los temas de El Archivo Curioso: estafas, desastres, mitos, cine, misterios y más."
    cuerpo = f"""<main class="ancho seccion">
<div class="seccion-cab"><h1 style="font-size:clamp(28px,5vw,42px); letter-spacing:-.02em">Temas</h1>
<span class="cuenta">{len(temas)} temas</span></div>
{chips_temas(temas, "../")}
</main>"""
    return pagina(f"Temas · {canal['nombre']}", cuerpo, canal, raiz="../", descripcion=descripcion,
                  ruta="temas/index.html")


def buscar(canal: dict) -> str:
    cuerpo = """<main class="ancho seccion lectura">
<h1 style="font-size:clamp(28px,5vw,42px); letter-spacing:-.02em">Buscar en el archivo</h1>
<label for="q" class="nota" style="display:block; margin-top:14px">Escribe un nombre, un lugar, un año o un tema</label>
<input id="q" class="buscador" type="search" autocomplete="off" placeholder="Ej.: Torre Eiffel, 1919, vampiros…">
<div id="cuenta" class="nota" aria-live="polite" style="margin-bottom:14px"></div>
<div id="resultados" class="rejilla"></div>
</main>"""
    return pagina(f"Buscar · {canal['nombre']}", cuerpo, canal, ruta="buscar.html",
                  descripcion="Busca entre todos los expedientes de El Archivo Curioso.", extra=BUSCAR_JS)


def inicio(canal: dict, expedientes: list[dict]) -> str:
    temas = temas_de(expedientes)
    # Solo las frases cuyo expediente ya está publicado; la primera va en el HTML y el navegador elige otra al azar
    por_num = {e["num"]: e for e in expedientes if e.get("num")}
    frases = [dict(p, u=f'expedientes/{por_num[p["num"]]["_slug"]}.html')
              for p in (canal.get("portadas") or PORTADAS) if p.get("num") in por_num]
    if not frases:
        frases = [{"antes": "Hay cosas que ", "tachado": "no deberías saber", "despues": ".", "u": "buscar.html"}]
    p = frases[0]
    frase = (f'<a href="{p["u"]}">{escape(p["antes"])}<span class="tachado">{escape(p["tachado"])}</span>'
             f'{escape(p["despues"])}</a>')
    abrir = f'<a class="boton" href="{p["u"]}">Abrir el expediente</a>'
    datos_frases = json.dumps(frases, ensure_ascii=False).replace("</", "<\\/")
    if expedientes:
        lista = ('<div class="filtros" role="group" aria-label="Filtrar">'
                 '<button class="activo" data-filtro="todos" aria-pressed="true">Todos</button>'
                 '<button data-filtro="video" aria-pressed="false">Vídeos</button>'
                 '<button data-filtro="short" aria-pressed="false">Shorts</button></div>')
        rejilla = f'<div class="rejilla">{"".join(ficha(e) for e in expedientes)}</div>'
    else:
        lista = ""
        rejilla = (f'<div class="vacio"><div class="logo">{LUPA_SVG}</div>'
                   '<p>Los primeros expedientes se están catalogando.<br>Muy pronto los encontrarás aquí.</p></div>')
    cuerpo = f"""<main class="ancho">
<section class="portada">
  <div class="linterna" aria-hidden="true"></div>
  <div class="vigilante" aria-hidden="true">{LUPA_SVG}</div>
  <div class="sello-rojo mono">Clasificado</div>
  <p class="susurro mono">Abriste el archivo a las <b data-hora>esta hora</b>. Nadie más lo sabe.</p>
  <h1 id="frase" aria-label="{escape(p['antes'] + p['tachado'] + p['despues'])}">{frase}</h1>
  <p class="pista">Pasa el ratón por lo tachado. O tócalo. Si te atreves.</p>
  <p class="desc">{escape(canal['lema'])}. Expedientes reales, con fuentes, de los que no se hablan en clase.</p>
  <div class="botones" id="abrir">{abrir}<a class="boton secundario sorprendeme" href="buscar.html">Sorpréndeme</a></div>
  <a class="bajar mono" href="#expedientes">↓ {len(expedientes)} expedientes abiertos</a>
  <script type="application/json" id="frases">{datos_frases}</script>
</section>
<section id="expedientes" class="seccion">
  <div class="seccion-cab"><div><h2>Expedientes abiertos</h2><span class="cuenta">{len(expedientes)} casos. Ninguno debería haber pasado.</span></div>{lista}</div>
  {rejilla}
</section>
<section class="seccion" style="padding-top:0">
  <div class="seccion-cab"><h2>Explora por temas</h2></div>
  {chips_temas(temas)}
</section>
</main>"""
    jsonld = [
        {"@context": "https://schema.org", "@type": "WebSite", "name": canal["nombre"], "url": f"{URL}/",
         "inLanguage": "es", "description": canal["descripcion"],
         "potentialAction": {"@type": "SearchAction", "target": f"{URL}/buscar.html?q={{q}}", "query-input": "required name=q"}},
        {"@context": "https://schema.org", "@type": "Organization", "name": canal["nombre"], "url": f"{URL}/",
         "logo": f"{URL}/logo.png", "sameAs": [canal["youtube"]]},
    ]
    return pagina(f"{canal['nombre']} | {canal['lema']}", cuerpo, canal, descripcion=canal["descripcion"],
                  extra=FRASE_JS + (FILTRO_JS if expedientes else ""), jsonld=jsonld)


def expediente(e: dict, anterior: dict | None, siguiente: dict | None, canal: dict) -> str:
    tipo = "short" if e.get("tipo") == "short" else "video"
    datos = "".join(f"<span><b>{k}:</b> {escape(v)}</span>" for k, v in (
        ("Lugar", e.get("lugar", "")), ("Publicado", fecha_larga(e["fecha"])),
        ("Formato", "Short" if tipo == "short" else "Vídeo")) if v)
    bloques = f'<div class="bloque caso"><h2>El caso</h2><p>{escape(e["resumen"])}</p></div>' if e.get("resumen") else ""
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
        bloques += ('<div class="bloque chips">'
                    + "".join(f'<a href="../temas/{slug(t)}.html">{escape(t)}</a>' for t in e["etiquetas"])
                    + "</div>")
    nav = '<nav class="navegacion" aria-label="Otros expedientes">'
    if anterior:
        nav += f'<a href="{anterior["_slug"]}.html"><small>← Anterior</small>{escape(anterior["titulo"])}</a>'
    if siguiente:
        nav += f'<a class="sig" href="{siguiente["_slug"]}.html"><small>Siguiente →</small>{escape(siguiente["titulo"])}</a>'
    nav += "</nav>"
    if e.get("youtube"):
        video = f"""<div class="reproductor {tipo}"><iframe src="https://www.youtube-nocookie.com/embed/{escape(e['youtube'])}"
  title="{escape(e['titulo'])}" loading="lazy" allowfullscreen
  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"></iframe></div>
<p class="ver-yt"><a href="https://www.youtube.com/watch?v={escape(e['youtube'])}">Ver en YouTube</a></p>"""
    else:
        # Aún no está en YouTube: miniatura y aviso de dónde verlo
        img = e["_img"] if e["_img"].startswith("http") else "../" + e["_img"]
        video = (f'<img src="{escape(img)}" alt="{escape(e["titulo"])}" style="display:block; width:100%; border-radius:14px">'
                 '<p class="ver-yt">El vídeo de este expediente ya está en '
                 '<a href="https://www.tiktok.com/@elarchivocurioso7" rel="noopener">TikTok</a> y muy pronto llegará a '
                 f'<a href="{escape(canal["youtube"])}">YouTube</a>.</p>')
    if e.get("_episodio"):
        ep = e["_episodio"]
        video += (f'<div class="bloque relacionado"><p>📜 Este Short es un adelanto. El expediente completo, con todo el '
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
        final = (f'<div class="sabes-demasiado"><p class="grande">Ya sabes demasiado.</p>'
                 f'<p class="peque">Pero el archivo no se acaba aquí.</p>'
                 f'<a class="boton" href="{otro["_slug"]}.html">Abrir el siguiente expediente</a></div>')
    cuerpo = f"""<div class="exposicion" aria-hidden="true"></div><div class="reloj mono" aria-hidden="true"></div>
<main class="ancho expediente"><div class="lectura">
<a class="volver" href="../index.html#expedientes">← Todos los expedientes</a>
<div class="ficha-num mono">Expediente {escape(num_ficha(e))}</div>
<h1 aria-label="{escape(e['titulo'])}">{titulo_html(e, enfocable=True)}</h1>
<div class="datos">{datos}</div>
{video}
{bloques}
{en_un_minuto}
{final}
{compartir(e, f"expedientes/{e['_slug']}.html")}
{nav}
</div></main>"""
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
                  ruta=ruta, imagen=imagen_compartir(e), tipo_og="video.other" if e.get("youtube") else "article", jsonld=jsonld,
                  extra=COPIAR_JS)


def imagen_compartir(e: dict) -> str:
    """Imagen al compartir el enlace: la tarjeta con el título tachado (og/<slug>.jpg) si ya está hecha."""
    propia = f"og/{e['_slug']}.jpg"
    return propia if (WEB / propia).exists() else e["_img"]


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
            for campo in ("articulo", "lecturas", "slug", "censura"):
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
    # Los Shorts que salen de un episodio cuentan lo mismo: tienen página (para YouTube y Google), pero no tarjeta;
    # se ven dentro de su episodio. En las listas solo salen los episodios y los Shorts independientes.
    listados = [e for e in visibles if not e.get("_episodio")]
    # Número de expediente en el archivo: por orden de publicación (el primero es el nº 001)
    for n, e in enumerate(reversed(listados), 1):
        e["_n"] = n
    for e in visibles:
        if e.get("_episodio"):
            e["_n"] = e["_episodio"]["_n"]

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

    # Enlace de cada vídeo de YouTube a su página (para ponerlo en las descripciones de YouTube).
    # La sincronización de albuuss depende de este formato: {ID: {num, titulo, url}}
    (SALIDA / "enlaces.json").write_text(json.dumps(
        {e["youtube"]: {"num": e.get("num", ""), "titulo": e["titulo"], "url": f"{URL}/expedientes/{e['_slug']}.html"}
         for e in visibles if e.get("youtube")}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Índice para Buscar y Sorpréndeme (rutas relativas a la raíz)
    # Datos para las imágenes de compartir (las dibuja Promocion/compartir.py; aquí solo el texto)
    (WEB / "datos" / "compartir.json").write_text(json.dumps(
        [dict(zip(("antes", "tachado", "despues"), partes_titulo(e)), slug=e["_slug"], num=num_ficha(e),
              img=e["_img"], tipo=e.get("tipo", "video")) for e in visibles],
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (SALIDA / "indice.json").write_text(json.dumps(
        [{"t": e["titulo"], "u": f"expedientes/{e['_slug']}.html", "r": e.get("resumen", ""),
          "e": e.get("etiquetas", []), "y": e.get("epoca", ""), "l": e.get("lugar", ""), "n": num_ficha(e)}
         for e in visibles], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    (SALIDA / "index.html").write_text(inicio(canal, listados), encoding="utf-8")
    (SALIDA / "buscar.html").write_text(buscar(canal), encoding="utf-8")
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
    entradas += [(f"{URL}/temas/{slug(t)}.html", max(e["fecha"][:10] for e in es)) for t, es in temas.items()]
    entradas.append((f"{URL}/temas/index.html", hoy))
    entradas.append((f"{URL}/acerca.html", hoy))
    entradas.append((f"{URL}/privacidad.html", hoy))
    (SALIDA / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{escape_xml(u)}</loc><lastmod>{f}</lastmod></url>\n" for u, f in entradas)
        + "</urlset>\n", encoding="utf-8")
    # Los buscadores de inteligencia artificial (ChatGPT, Perplexity, Claude, Gemini) también pueden leer y citar la web
    robots_ia = "".join(f"User-agent: {b}\nAllow: /\n\n" for b in (
        "OAI-SearchBot", "ChatGPT-User", "GPTBot", "PerplexityBot", "ClaudeBot", "Claude-SearchBot", "Google-Extended",
        "Bingbot"))
    (SALIDA / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\n{robots_ia}Sitemap: {URL}/sitemap.xml\n",
                                       encoding="utf-8")
    # llms.txt: resumen del archivo para los asistentes de IA (propuesta llmstxt.org)
    lineas = [f"# {canal['nombre']}", "", f"> {canal['lema']}. {canal['descripcion']}", "",
              "Archivo en español de historias reales que parecen inventadas: sucesos insólitos, mitos desmontados, "
              "crímenes antiguos y curiosidades de cine e historia. Cada expediente tiene un artículo con fuentes, "
              "una sección de qué es mito y qué no, y su vídeo en YouTube.", "", "## Expedientes", ""]
    lineas += [f"- [{e['titulo']}]({URL}/expedientes/{e['_slug']}.html): {e.get('resumen', '')}" for e in listados]
    lineas += ["", "## Temas", ""] + [f"- [{t}]({URL}/temas/{slug(t)}.html)" for t in temas]
    lineas += ["", "## Más", "", f"- [Acerca del archivo y cómo trabajamos]({URL}/acerca.html)",
               f"- [Canal de YouTube]({canal['youtube']})", ""]
    (SALIDA / "llms.txt").write_text("\n".join(lineas), encoding="utf-8")

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
