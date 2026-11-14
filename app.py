"""TiendaControl - interfaz web del prototipo funcional (Streamlit).

Front diseñado en Figma (Tienda La Esquina). La lógica de negocio vive en el paquete
`tiendacontrol` (clases Python); este archivo solo dibuja pantallas y llama a esas clases.
Ejecutar:  python -m streamlit run app.py
"""
import base64
import csv
import html
import io
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import streamlit as st

from tiendacontrol import Usuario, Producto, Cliente, Inventario, ErrorNegocio, PermisoDenegado

st.set_page_config(page_title="TiendaControl", page_icon="🛒", layout="wide",
                   initial_sidebar_state="expanded")

# ===================================================================== Utilidades
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
MES_CORTO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
COLOMBIA = timezone(timedelta(hours=-5))
TIENDA = "Tienda La Esquina"
CIUDAD = "Bogotá, Colombia"
UNIDAD = {"004": "cubetas"}  # unidad de venta; por defecto "un."


def esc(t) -> str:
    return html.escape(str(t)).replace("$", "&#36;")


def cop(x) -> str:
    """Pesos colombianos para HTML: $12.600"""
    return "&#36;" + f"{x:,.0f}".replace(",", ".")


def h(s: str) -> str:
    """Compacta HTML en una línea (evita que markdown lo trate como bloque de código)."""
    return "".join(l.strip() for l in s.splitlines())


def hoy() -> date:
    return date.today()


def fecha_larga(d: date) -> str:
    return f"{DIAS[d.weekday()]}, {d.day} de {MESES[d.month - 1]} de {d.year}"


def fecha_corta(d: date) -> str:
    return f"{d.day} {MES_CORTO[d.month - 1]}"


def fecha_media(d: date) -> str:
    return f"{d.day} {MES_CORTO[d.month - 1]} {d.year}"


def hora12(dt: datetime) -> str:
    h12 = dt.hour % 12 or 12
    return f"{h12}:{dt.minute:02d} {'a. m.' if dt.hour < 12 else 'p. m.'}"


def ahora() -> datetime:
    return datetime.now(COLOMBIA)


def uds(p: Producto, n: int) -> str:
    return f"{n} {UNIDAD.get(p.codigo, 'un.')}"


def corto(nombre: str) -> str:
    """'Arroz Diana 500 g' -> 'Arroz Diana'"""
    out = []
    for w in nombre.split():
        if any(c.isdigit() for c in w) or w == "×":
            break
        out.append(w)
    return " ".join(out) or nombre


def tiempo_restante(d: date) -> str:
    n = (d - hoy()).days
    if n < 0:
        return f"Vencido hace {-n} día{'s' if n != -1 else ''}"
    if n == 0:
        return "Vence hoy"
    if n == 1:
        return "Mañana"
    return f"En {n} días"


# ============================================================ Datos de ejemplo (sesión)
USUARIOS = {
    "dueno": Usuario("María Rodríguez", "propietario", "1234"),
    "empleado": Usuario("Camilo Pérez", "empleado", "abcd"),
}
ALIAS = {"maria.rodriguez": "dueno", "camilo.perez": "empleado"}
ROL_ETIQUETA = {"propietario": "Propietaria", "empleado": "Empleado"}


def datos_de_ejemplo():
    """Datos de ejemplo que coinciden con la guía de verificación del documento entregado."""
    inv, d = Inventario(), hoy()
    codigos = {}

    def lote(prod, cant, costo, dias=None, codigo=None):
        l = prod.registrar_entrada(cant, costo, d + timedelta(days=dias) if dias is not None else None)
        if codigo:
            codigos[l.id] = codigo

    arroz = Producto("001", "Arroz Diana 1 kg", "Granos", 4200, 5)
    lote(arroz, 20, 3300, 180)
    leche = Producto("002", "Leche Alquería 1 L", "Lácteos", 4500, 6)
    lote(leche, 4, 3600, 6, "L-241")      # vence antes: se vende primero (RN-02)
    lote(leche, 12, 3700, 25, "L-242")
    gaseosa = Producto("003", "Gaseosa 1,5 L", "Bebidas", 3000, 5)
    lote(gaseosa, 10, 2000)               # 10 a $2.000 + 20 a $2.300 -> costo promedio $2.200 (RN-06)
    lote(gaseosa, 20, 2300)
    huevos = Producto("004", "Huevos AA × 30", "Huevos", 18000, 3)
    lote(huevos, 10, 14500, 20)
    yogur = Producto("005", "Yogur Alpina 200 g", "Lácteos", 3200, 6)
    lote(yogur, 18, 2400, 40, "Y-108")
    pan = Producto("006", "Pan tajado Bimbo 450 g", "Panadería", 6500, 6)
    lote(pan, 16, 4900, 20, "P-062")
    cafe = Producto("007", "Café Sello Rojo 250 g", "Despensa", 9800, 8)
    lote(cafe, 24, 7500, 300)
    for p in (arroz, leche, gaseosa, huevos, yogur, pan, cafe):
        inv.agregar_producto(p)

    inv.agregar_cliente(Cliente("Ana Pérez", 50000))   # límite $50.000 (RN-07)
    inv.agregar_cliente(Cliente("Luis Gómez", 100000))
    inv.clientes["Ana Pérez"].registrar_deuda(0, d - timedelta(days=35), 40000)  # saldo $40.000, 35 días (RN-09)
    return inv, {}, codigos


ss = st.session_state
if "inv" not in ss:
    ss.inv, ss.horas, ss.codigos = datos_de_ejemplo()
    ss.usuario = None
    ss.page = "alertas"
    ss.panel = None
    ss.flash = None
inv: Inventario = ss.inv


def codigo_lote(l) -> str:
    return ss.codigos.get(l.id, f"L-{l.id:03d}")


# =========================================================================== Estilos
LOGO = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round"><path d="M4 9l1.5-5h13L20 9"/>'
        '<path d="M4 9v11h16V9"/><path d="M4 9c0 1.7 1.3 3 3 3s3-1.3 3-3c0 1.7 1.3 3 3 3s3-1.3 3-3c0 1.7 1.3 3 3 3"/>'
        '<path d="M10 20v-4h4v4"/></svg>')
ICONO = {
    "caja": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7l9-4 9 4v10l-9 4-9-4z"/><path d="M3 7l9 4 9-4M12 11v10"/></svg>',
    "reloj": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="13" r="8"/><path d="M12 9v4l3 2M9 3h6"/></svg>',
    "alarma": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="13" r="7.5"/><path d="M12 9v4l2.5 1.5M4 5l3-2M20 5l-3-2"/></svg>',
    "billete": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/></svg>',
    "tendencia": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l6-6 4 4 8-8M15 7h6v6"/></svg>',
    "alerta": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/></svg>',
    "gente": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6M16 4.5a3.5 3.5 0 010 7M18 14.5c2.2.6 3.5 2.4 3.5 5.5"/></svg>',
    "info": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.5"/></svg>',
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root{--verde:#2E7D32;--verde-osc:#205C26;--verde-claro:#E8F3E6;--fondo:#F7F7F5;--borde:#E6E7E1;
--texto:#1B261D;--gris:#6B7280;--naranja:#B45309;--naranja-bg:#FFF1DC;--rojo:#C62828;--rojo-bg:#FDEDED;}
html,body,.stApp,.stApp *:not([data-testid="stIconMaterial"]){font-family:'Inter',sans-serif;}
.stApp{background:var(--fondo);color:var(--texto);}
header[data-testid="stHeader"]{background:transparent;}
[data-testid="stToolbar"],[data-testid="stDecoration"],footer{visibility:hidden;height:0;}
.block-container{padding:1.1rem 2.4rem 3rem;max-width:1200px;}
/* ---------- barra lateral */
section[data-testid="stSidebar"]{background:#fff;border-right:1px solid var(--borde);width:272px !important;min-width:272px !important;}
section[data-testid="stSidebar"] > div{padding-top:.4rem;}
[data-testid="stSidebarUserContent"]{padding:1rem .9rem;}
.tc-marca{display:flex;align-items:center;gap:.6rem;font-size:1.15rem;font-weight:600;margin:.2rem 0 1rem;}
.tc-marca .ico{width:34px;height:34px;border-radius:9px;background:var(--verde);color:#fff;display:flex;align-items:center;justify-content:center;}
.tc-marca .ico svg{width:20px;height:20px;}
.tc-tienda{background:var(--fondo);border-radius:10px;padding:.65rem .8rem;margin-bottom:.9rem;font-size:.82rem;}
.tc-tienda b{display:block;font-weight:600;font-size:.86rem;}.tc-tienda span{color:var(--gris);font-size:.74rem;}
section[data-testid="stSidebar"] .stButton > button{width:100%;justify-content:flex-start;background:transparent;border:0;color:#3B463E;font-weight:500;font-size:.9rem;padding:.55rem .8rem;border-radius:9px;box-shadow:none;display:flex;align-items:center;}
section[data-testid="stSidebar"] .stButton > button:hover{background:var(--fondo);color:var(--texto);}
section[data-testid="stSidebar"] .stButton{margin-bottom:-.25rem;}
.tc-usuario{display:flex;align-items:center;gap:.6rem;border-top:1px solid var(--borde);padding-top:.9rem;margin-top:.8rem;}
.tc-avatar{width:30px;height:30px;border-radius:50%;background:var(--verde-claro);color:var(--verde-osc);font-weight:600;font-size:.7rem;display:flex;align-items:center;justify-content:center;}
.tc-usuario b{display:block;font-size:.8rem;font-weight:600;}.tc-usuario span{font-size:.72rem;color:var(--gris);}
.tc-lema{background:var(--verde-claro);border-radius:10px;padding:.7rem .8rem;font-size:.76rem;color:#3B5A3E;margin-top:.8rem;}
.tc-lema b{display:block;color:var(--verde-osc);font-weight:600;margin-bottom:.1rem;}
/* ---------- barra superior y encabezados */
.tc-top{display:flex;justify-content:space-between;align-items:center;font-size:.8rem;color:var(--gris);padding:.2rem 0 1rem;border-bottom:1px solid var(--borde);margin-bottom:1.4rem;gap:1rem;flex-wrap:wrap;}
.tc-top b{color:var(--texto);font-weight:600;}.tc-top .sep{margin:0 .4rem;}
.tc-pill{display:inline-block;background:var(--verde-claro);color:var(--verde-osc);border-radius:999px;padding:.15rem .7rem;font-size:.74rem;font-weight:600;margin-left:.7rem;}
.tc-eyebrow{font-size:.68rem;font-weight:700;letter-spacing:.09em;color:var(--verde);text-transform:uppercase;}
.tc-h1{font-size:2rem;font-weight:700;line-height:1.15;margin:.25rem 0 .35rem;color:var(--texto);}
.tc-sub{color:var(--gris);font-size:.93rem;margin-bottom:1.3rem;}
/* ---------- tarjetas */
.tc-card{background:#fff;border:1px solid var(--borde);border-radius:14px;padding:1.05rem 1.2rem;margin-bottom:1rem;}
.tc-kpi{position:relative;min-height:112px;}
.tc-kpi .t{font-size:.82rem;color:var(--gris);}
.tc-kpi .v{font-size:1.85rem;font-weight:700;margin:.15rem 0 .2rem;line-height:1.15;}
.tc-kpi .s{font-size:.76rem;}
.tc-kpi .i{position:absolute;right:1rem;top:1rem;width:20px;height:20px;}
.tc-kpi .i svg{width:20px;height:20px;}
.tono-naranja{color:var(--naranja);}.tono-rojo{color:var(--rojo);}.tono-gris{color:var(--gris);}.tono-verde{color:var(--verde);}
.tc-sec{display:flex;justify-content:space-between;align-items:center;margin:.4rem 0 .6rem;}
.tc-sec h3{font-size:1.05rem;font-weight:600;margin:0;padding:0;color:var(--texto);}
.tc-badge{background:#F1F2EE;color:#555F57;border-radius:999px;padding:.15rem .65rem;font-size:.72rem;font-weight:500;}
.tc-badge.nar{background:var(--naranja-bg);color:var(--naranja);}
.tc-tabla{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--borde);border-radius:14px;overflow:hidden;font-size:.85rem;border-spacing:0;}
.tc-wrap{background:#fff;border:1px solid var(--borde);border-radius:14px;overflow-x:auto;margin-bottom:1rem;}
.tc-wrap table{width:100%;border-collapse:collapse;font-size:.85rem;min-width:520px;margin:0 !important;border:0 !important;}
.tc-wrap th,.tc-wrap td{border:0 !important;}
.tc-wrap th{background:#F4F5F1;color:#555F57;font-weight:500;font-size:.74rem;text-align:left;padding:.7rem 1rem;}
.tc-wrap td{padding:.95rem 1rem;border-top:1px solid #EEEFEA !important;vertical-align:middle;}
.tc-wrap td.r,.tc-wrap th.r{text-align:right;}
.tc-wrap .pie{padding:.75rem 1rem;color:var(--gris);font-size:.76rem;border-top:1px solid #EEEFEA;}
.tc-wrap .anulada td{color:#9AA09B;text-decoration:line-through;}
.tc-pago{border-radius:999px;padding:.12rem .6rem;font-size:.74rem;font-weight:500;}
.tc-pago.contado{background:var(--verde-claro);color:var(--verde-osc);}.tc-pago.credito{background:var(--naranja-bg);color:var(--naranja);}
.tc-aviso{border-radius:12px;padding:.8rem 1rem;font-size:.85rem;margin:.4rem 0 1rem;display:flex;gap:.7rem;align-items:flex-start;}
.tc-aviso svg{width:20px;height:20px;flex:none;margin-top:1px;}
.tc-aviso b{display:block;font-weight:600;margin-bottom:.1rem;}
.tc-aviso.ok{background:var(--verde-claro);color:var(--verde-osc);}
.tc-aviso.err{background:var(--rojo-bg);color:var(--rojo);}
.tc-aviso.nar{background:var(--naranja-bg);color:var(--naranja);}
.tc-aviso.info{background:#EEF1EC;color:#3B463E;}
.tc-resumen{background:#F4F5F1;border:1px solid var(--borde);border-radius:12px;padding:1rem 1.1rem;}
.tc-resumen .fila{display:flex;justify-content:space-between;font-size:.88rem;}
.tc-resumen .tit{font-weight:600;margin-bottom:.6rem;}
.tc-resumen .tot{font-size:1.9rem;font-weight:700;margin:.2rem 0 .6rem;}
.tc-resumen hr{border:0;border-top:1px solid var(--borde);margin:.7rem 0;}
.tc-resumen .cli b{display:block;font-size:.88rem;}.tc-resumen .cli span{display:block;font-size:.8rem;color:var(--gris);}
.tc-nota{font-size:.78rem;color:var(--gris);margin:.4rem 0 .9rem;}
.tc-campo{font-size:.78rem;color:var(--gris);margin:-.5rem 0 .8rem;}
.tc-campo.err{color:var(--rojo);}
.tc-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;}
.tc-stats .t{font-size:.78rem;color:var(--gris);}.tc-stats .v{font-size:1.2rem;font-weight:700;margin-top:.15rem;}
/* ---------- formularios (widgets de Streamlit) */
label[data-testid="stWidgetLabel"] p,label p{font-size:.82rem !important;font-weight:500 !important;color:var(--texto);}
[data-baseweb="input"],[data-baseweb="base-input"],[data-baseweb="select"] > div{background:#fff !important;border-color:#E1E3DC !important;border-radius:10px !important;}
[data-baseweb="input"] input{background:#fff !important;font-size:.9rem;}
.stTextInput > div > div,.stNumberInput > div > div{border-radius:10px;}
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div[data-testid="stVerticalBlock"] .st-key-marca){border-radius:14px;}
[data-testid="stBaseButton-primary"]{background:var(--verde);border:1px solid var(--verde);color:#fff;border-radius:10px;font-weight:600;font-size:.88rem;padding:.55rem 1.1rem;}
[data-testid="stBaseButton-primary"]:hover{background:var(--verde-osc);border-color:var(--verde-osc);color:#fff;}
[data-testid="stBaseButton-primary"]:disabled{background:#E2E6DF;border-color:#E2E6DF;color:#8B948C;}
.st-key-alert_entrada button,.st-key-btn_nuevo button,.st-key-btn_entrada button,.st-key-btn_baja button{white-space:nowrap;}
[data-testid="stBaseButton-secondary"],[data-testid="stDownloadButton"] button{background:#fff;border:1px solid var(--borde);color:var(--texto);border-radius:10px;font-weight:500;font-size:.86rem;}
[data-testid="stBaseButton-secondary"]:hover{border-color:var(--verde);color:var(--verde-osc);}
section.main .st-key-btn_baja button,.st-key-btn_baja button{color:var(--rojo) !important;border-color:#E9A9A9 !important;}
.st-key-btn_nuevo button{background:var(--verde) !important;color:#fff !important;border-color:var(--verde) !important;}
.st-key-v_pago [data-testid="stRadioGroup"]{display:grid !important;grid-template-columns:1fr 1fr;gap:.6rem;width:100%;}
.st-key-v_pago [data-testid="stRadioGroup"] > div{width:100%;flex:1 1 0;min-width:0;}
.st-key-v_pago label[data-testid="stRadioOption"]{background:#fff;border:1px solid #E1E3DC;border-radius:10px;padding:.7rem .9rem;margin:0;width:100%;justify-content:center;}
.st-key-v_pago label[data-testid="stRadioOption"][data-selected="true"]{background:var(--verde-claro);border-color:#9CC79F;}
[data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"]{gap:.6rem;}
div[data-testid="stVerticalBlockBorderWrapper"]{background:#fff;border-radius:14px;border-color:var(--borde);}
@media (max-width:800px){.block-container{padding:1rem 1rem 3rem;}.tc-stats{grid-template-columns:1fr;}.tc-h1{font-size:1.6rem;}}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ===================================================================== Componentes
def aviso(tipo: str, titulo: str, texto: str = "", icono: str = "info") -> None:
    cuerpo = f"<div><b>{esc(titulo)}</b>{esc(texto)}</div>" if texto else f"<div>{esc(titulo)}</div>"
    st.markdown(h(f'<div class="tc-aviso {tipo}">{ICONO[icono]}{cuerpo}</div>'), unsafe_allow_html=True)


def mostrar_flash() -> None:
    if ss.flash:
        tipo, msg = ss.flash
        aviso("ok" if tipo == "ok" else "err", msg, icono="info" if tipo == "ok" else "alerta")
        ss.flash = None


def cabecera(eyebrow: str, titulo: str, sub: str) -> None:
    u = ss.usuario_obj
    pagina = dict((s, n) for s, n, _ in PAGINAS)[ss.page]
    st.markdown(h(f'''<div class="tc-top"><div>{esc(TIENDA)}<span class="sep">›</span><b>{esc(pagina)}</b></div>
    <div>{esc(fecha_larga(hoy()))}<span class="tc-pill">{ROL_ETIQUETA[u.rol]}</span></div></div>
    <div class="tc-eyebrow">{esc(eyebrow)}</div><div class="tc-h1">{esc(titulo)}</div><div class="tc-sub">{esc(sub)}</div>'''),
                unsafe_allow_html=True)


def kpi(titulo, valor, sub, tono="gris", icono="caja") -> str:
    return h(f'''<div class="tc-card tc-kpi"><div class="t">{esc(titulo)}</div><div class="v">{valor}</div>
    <div class="s tono-{tono}">{sub}</div><div class="i tono-{tono}">{ICONO[icono]}</div></div>''')


def seccion(titulo: str, badge: str = "", nar: bool = False) -> None:
    b = f'<span class="tc-badge{" nar" if nar else ""}">{esc(badge)}</span>' if badge else ""
    st.markdown(h(f'<div class="tc-sec"><h3>{esc(titulo)}</h3>{b}</div>'), unsafe_allow_html=True)


def tabla(cabeceras, filas, pie="", derecha=(), clases_fila=None) -> None:
    th = "".join(f'<th class="{"r" if i in derecha else ""}">{esc(c)}</th>' for i, c in enumerate(cabeceras))
    trs = ""
    for n, f in enumerate(filas):
        cls = clases_fila[n] if clases_fila else ""
        trs += f'<tr class="{cls}">' + "".join(
            f'<td class="{"r" if i in derecha else ""}">{c}</td>' for i, c in enumerate(f)) + "</tr>"
    p = f'<div class="pie">{pie}</div>' if pie else ""
    st.markdown(h(f'<div class="tc-wrap"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>{p}</div>'),
                unsafe_allow_html=True)


def cambiar_pagina(slug: str, panel=None) -> None:
    ss.page = slug
    ss.panel = panel


# ============================================================= Inicio de sesión (HU-01)
def pantalla_login() -> None:
    st.markdown("<style>[data-testid='stMainBlockContainer'] > [data-testid='stVerticalBlock']{gap:0 !important;}header[data-testid='stHeader']{display:none !important;}.st-key-login_izq img{width:100% !important;height:auto !important;}section[data-testid='stSidebar'],[data-testid='stSidebarCollapsedControl'],"
                "[data-testid='collapsedControl']{display:none !important;}"
                ".block-container{padding:0 !important;max-width:100% !important;}"
                "[data-testid='stHorizontalBlock']{gap:0 !important;}"
                ".st-key-login_izq{background:#205C26;min-height:100vh;padding:2.6rem 3rem;color:#fff;}"
                ".st-key-login_der{min-height:100vh;padding:14vh 14% 2rem;background:#F7F7F5;}"
                ".st-key-login_der [data-testid='stForm']{border:0;padding:0;background:transparent;}"
                ".st-key-login_der .stButton button,.st-key-login_der [data-testid='stBaseButton-primaryFormSubmit']{width:100%;}"
                ".tc-movil{display:none;}"
                "@media (max-width:800px){.st-key-login_izq{display:none;}.st-key-login_der{padding:2rem 1.3rem;min-height:auto;}.tc-movil{display:flex;}}"
                "</style>", unsafe_allow_html=True)
    izq, der = st.columns([1.05, 1], gap="small")
    foto = Path(__file__).parent / "assets" / "tienda.jpg"
    img = ""
    if foto.exists():
        b64 = base64.b64encode(foto.read_bytes()).decode()
        img = f'<img src="data:image/jpeg;base64,{b64}" style="width:100%;border-radius:16px;margin-top:1.6rem;display:block;">'
    with izq:
        with st.container(key="login_izq"):
            st.markdown(h(f'''<div class="tc-marca" style="color:#fff"><div class="ico" style="background:#fff;color:#205C26">{LOGO}</div>TiendaControl</div>
            <div style="margin-top:3.2rem;font-size:2.3rem;font-weight:500;line-height:1.2">Tu tienda, en orden.<br>Tu día, más tranquilo.</div>
            <div style="margin-top:1rem;font-size:.95rem;color:#CFE3D1;line-height:1.5">Inventario, ventas y fiado en un solo lugar.<br>Sin enredos, como debe ser.</div>
            {img}
            <div style="margin-top:1.1rem;font-size:.8rem;color:#CFE3D1">♡ Hecho para quienes mueven el barrio.</div>'''),
                        unsafe_allow_html=True)
    with der:
        with st.container(key="login_der"):
            st.markdown(h(f'''<div class="tc-marca tc-movil"><div class="ico">{LOGO}</div>TiendaControl</div>
            <div class="tc-eyebrow">Bienvenido a tu tienda</div><div class="tc-h1">Qué bueno verte.</div>
            <div class="tc-sub">Ingresa para llevar las cuentas y tener tu negocio al día.</div>'''), unsafe_allow_html=True)
            with st.form("login", border=False):
                usuario = st.text_input("Usuario", placeholder="maria.rodriguez")
                clave = st.text_input("Clave", type="password", placeholder="••••••••••")
                enviar = st.form_submit_button("Ingresar", type="primary", icon=":material/arrow_forward:", width="stretch")
            if enviar:
                clave_u = ALIAS.get(usuario.strip().lower(), usuario.strip().lower())
                u = USUARIOS.get(clave_u)
                if u is None:
                    aviso("err", "Usuario no encontrado.", icono="alerta")
                elif not u.verificar_clave(clave):
                    aviso("err", "Clave incorrecta.", icono="alerta")
                else:
                    ss.usuario, ss.page, ss.panel = clave_u, "alertas", None
                    st.rerun()
            st.markdown(h(f'''<div class="tc-aviso info" style="margin-top:1rem">{ICONO["info"]}<div><b>¿No puedes ingresar?</b>
            Pídele al propietario que revise tu usuario o te ayude con la clave.</div></div>
            <div class="tc-nota" style="text-align:center">Cuentas de prueba: <b>dueno</b> / 1234 · <b>empleado</b> / abcd</div>
            <div class="tc-nota" style="text-align:center">🔒 Tu información, solo para tu negocio.</div>'''),
                        unsafe_allow_html=True)


if ss.usuario is None:
    pantalla_login()
    st.stop()

ss.usuario_obj = USUARIOS[ss.usuario]
user: Usuario = ss.usuario_obj
es_dueno = user.es_propietario

# ====================================================================== Barra lateral
PAGINAS = [("alertas", "Alertas", ":material/notifications:"),
           ("inventario", "Inventario", ":material/inventory_2:"),
           ("ventas", "Ventas", ":material/shopping_basket:"),
           ("clientes", "Clientes y fiado", ":material/group:")]
if es_dueno:
    PAGINAS += [("reportes", "Reportes", ":material/trending_up:"),
                ("bitacora", "Bitácora", ":material/assignment:")]
if ss.page not in dict((s, n) for s, n, _ in PAGINAS):
    ss.page = "alertas"

n_alertas = len(inv.productos_por_agotarse()) + len(inv.lotes_por_vencer(7))
iniciales = "".join(w[0] for w in user.nombre.split()[:2]).upper()
st.markdown(f"""<style>
.st-key-nav_{ss.page} button{{background:#E8F3E6 !important;color:#205C26 !important;font-weight:600 !important;}}
section[data-testid="stSidebar"] .stButton button > div{{width:100%;}}
section[data-testid="stSidebar"] .stButton button > div > span{{width:100%;display:flex;align-items:center;}}
.st-key-nav_alertas button > div > span::after{{content:"{n_alertas}";margin-left:auto;font-size:.72rem;font-weight:600;color:#B45309;}}
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown(h(f'''<div class="tc-marca"><div class="ico">{LOGO}</div>TiendaControl</div>
    <div class="tc-tienda"><b>{esc(TIENDA)}</b><span>{esc(CIUDAD)}</span></div>'''), unsafe_allow_html=True)
    for slug, nombre, icono in PAGINAS:
        st.button(nombre, key=f"nav_{slug}", icon=icono, on_click=cambiar_pagina, args=(slug,))
    st.markdown(h(f'''<div class="tc-usuario"><div class="tc-avatar">{esc(iniciales)}</div>
    <div><b>{esc(user.nombre)}</b><span>{ROL_ETIQUETA[user.rol]}</span></div></div>'''), unsafe_allow_html=True)

    def cerrar():
        ss.usuario, ss.panel, ss.flash = None, None, None
    st.button("Cerrar sesión", key="nav_salir", icon=":material/logout:", on_click=cerrar)
    st.markdown(h('<div class="tc-lema"><b>Tu tienda, en orden.</b>Cada venta y cada peso cuentan.</div>'),
                unsafe_allow_html=True)


# =================================================================== Alertas (HU-03)
def pagina_alertas() -> None:
    cabecera("Lo importante de hoy", f"Hola, {user.nombre.split()[0]}",
             "Revisa qué hace falta y qué debes vender primero.")
    mostrar_flash()
    dias = int(ss.get("dias_venc", "30 días").split()[0])
    bajos = inv.productos_por_agotarse()
    venc = sorted(inv.lotes_por_vencer(dias), key=lambda t: t[1].vence)
    todos = sorted([(p, l) for p in inv.productos.values() for l in p.lotes
                    if l.cantidad > 0 and l.vence], key=lambda t: t[1].vence)
    c1, c2, c3 = st.columns(3)
    c1.markdown(kpi("Productos por agotarse", f"{len(bajos)} productos",
                    "Necesitan reposición" if bajos else "Todo en orden", "naranja" if bajos else "verde", "caja"),
                unsafe_allow_html=True)
    c2.markdown(kpi("Lotes próximos a vencer", f"{len(venc)} lotes", f"Dentro de los próximos {dias} días",
                    "naranja" if venc else "verde", "reloj"), unsafe_allow_html=True)
    if todos:
        p0, l0 = todos[0]
        c3.markdown(kpi("Atención más urgente", fecha_corta(l0.vence), f"{esc(corto(p0.nombre))} · {esc(uds(p0, l0.cantidad))}",
                        "rojo", "alarma"), unsafe_allow_html=True)
    else:
        c3.markdown(kpi("Atención más urgente", "—", "Sin lotes con vencimiento", "gris", "alarma"), unsafe_allow_html=True)

    seccion("Productos por agotarse", f"{len(bajos)} productos", nar=False)
    if bajos:
        tabla(["Código", "Producto", "Existencias", "Stock mínimo", "Faltan"],
              [[esc(p.codigo), f"<b>{esc(p.nombre)}</b>", f'<span class="tono-naranja">{esc(uds(p, p.existencias))}</span>',
                esc(uds(p, p.stock_minimo)), f'<span class="tono-rojo">{esc(uds(p, p.stock_minimo - p.existencias))}</span>']
               for p in bajos],
              pie="Repón al menos las unidades que faltan para llegar al stock mínimo.")
    else:
        aviso("ok", "Sin productos por agotarse.", icono="info")
    _, b = st.columns([2.4, 1.3])
    b.button("Registrar entrada de mercancía", key="alert_entrada", type="primary", icon=":material/inventory_2:",
             disabled=not es_dueno, on_click=cambiar_pagina, args=("inventario", "entrada"), width="stretch",
             help=None if es_dueno else "Solo el propietario registra entradas.")

    t1, t2 = st.columns([4, 1])
    with t1:
        seccion("Lotes próximos a vencer")
    t2.selectbox("Ventana", ["7 días", "15 días", "30 días"], index=2, key="dias_venc", label_visibility="collapsed")
    if venc:
        tabla(["Producto", "Lote", "Cantidad", "Vencimiento", "Tiempo restante"],
              [[f"<b>{esc(p.nombre)}</b>", esc(codigo_lote(l)), esc(uds(p, l.cantidad)), esc(fecha_media(l.vence)),
                f'<span class="{"tono-rojo" if (l.vence - hoy()).days <= 3 else "tono-naranja"}">{esc(tiempo_restante(l.vence))}</span>']
               for p, l in venc],
              pie=f"Mostrando {len(venc)} lote{'s' if len(venc) != 1 else ''} · Ordenados por la fecha más cercana.")
    else:
        aviso("ok", "Sin lotes por vencer en ese período.", icono="info")
    aviso("nar", "Pon estos productos a la vista",
          "Vende primero los lotes que vencen antes. No vendas productos vencidos.", "alerta")


# ============================================================ Inventario (HU-02, HU-10)
def pagina_inventario() -> None:
    if es_dueno:
        cabecera("Productos de tu tienda", "Inventario", "Consulta precios, revisa existencias y mantén la mercancía al día.")
    else:
        cabecera("Tu jornada en la tienda", "Inventario de empleado", "Consulta precios, revisa existencias y mantén la mercancía al día.")
        aviso("ok", f"Sesión de empleado · {user.nombre}",
              "Puedes consultar productos y registrar ventas. Los costos y los reportes son privados del propietario.", "info")
    mostrar_flash()

    if es_dueno:
        b1, b2, b3, _ = st.columns([1.35, 2.5, 1.3, 2.2])
        b1.button("Nuevo producto", key="btn_nuevo", type="primary", icon=":material/add:",
                  on_click=lambda: setattr(ss, "panel", "nuevo"))
        b2.button("Registrar entrada de mercancía", key="btn_entrada", icon=":material/inventory_2:",
                  on_click=lambda: setattr(ss, "panel", "entrada"))
        b3.button("Dar de baja", key="btn_baja", icon=":material/delete:",
                  on_click=lambda: setattr(ss, "panel", "baja"))
        if ss.panel:
            panel_inventario()

    f1, f2 = st.columns([3, 1])
    texto = f1.text_input("Buscar producto", placeholder="Nombre o código del producto", key="busca")
    cats = ["Todas las categorías"] + sorted({p.categoria for p in inv.productos.values()})
    cat = f2.selectbox("Categoría", cats, key="cat")
    total, bajos = len(inv.productos), inv.productos_por_agotarse()
    st.markdown(h(f'<div class="tc-sec"><b style="font-size:.85rem">{total} productos registrados</b>'
                  f'<span class="tc-badge nar">{len(bajos)} con stock bajo</span></div>'), unsafe_allow_html=True)
    vistos = [p for p in inv.productos.values()
              if (cat == "Todas las categorías" or p.categoria == cat)
              and (not texto.strip() or texto.strip().lower() in p.nombre.lower() or texto.strip().lower() in p.codigo.lower())]
    cab = ["Código", "Producto", "Categoría", "Precio", "Existencias", "Stock mínimo"] + (["Costo promedio"] if es_dueno else [])
    filas = []
    for p in vistos:
        clase = "tono-naranja" if p.por_agotarse() else ""
        fila = [esc(p.codigo), f"<b>{esc(p.nombre)}</b>", esc(p.categoria), cop(p.precio_venta),
                f'<span class="{clase}">{esc(uds(p, p.existencias))}</span>', esc(uds(p, p.stock_minimo))]
        if es_dueno:
            fila.append(cop(p.costo_promedio))
        filas.append(fila)
    if filas:
        pie = ("Mostrando todos los productos" if len(vistos) == total else f"Mostrando {len(vistos)} de {total} productos")
        tabla(cab, filas, pie=f"{pie} · Actualizado hoy a las {hora12(ahora())}")
    else:
        aviso("info", "No encontramos productos con esa búsqueda.", icono="info")
    if bajos:
        nombres = [corto(p.nombre) for p in bajos]
        lista = nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]
        aviso("nar", f"{len(bajos)} producto{'s' if len(bajos) != 1 else ''} necesita{'n' if len(bajos) != 1 else ''} reposición",
              f"{lista} {'está' if len(bajos) == 1 else 'están'} por debajo de su stock mínimo.", "alerta")
    if es_dueno:
        st.markdown('<div class="tc-nota">El costo promedio se calcula con las entradas de mercancía. '
                    'Solo tú, como propietaria, puedes verlo.</div>', unsafe_allow_html=True)


def panel_inventario() -> None:
    def cerrar():
        ss.panel = None
    with st.container(border=True, key="panel_inv"):
        if ss.panel == "nuevo":
            seccion("Nuevo producto")
            with st.form("f_nuevo", border=False):
                c1, c2, c3 = st.columns(3)
                cod, nom, cat = c1.text_input("Código"), c2.text_input("Nombre"), c3.text_input("Categoría")
                pv = c1.number_input("Precio de venta", min_value=0, step=100)
                sm = c2.number_input("Stock mínimo", min_value=0, step=1)
                g = st.form_submit_button("Guardar producto", type="primary")
            if g:
                if cod.strip() and nom.strip() and cod.strip() not in inv.productos:
                    inv.agregar_producto(Producto(cod.strip(), nom.strip(), cat.strip() or "General", pv, int(sm)))
                    ss.flash, ss.panel = ("ok", f"Producto {nom.strip()} creado con existencias en cero."), None
                    st.rerun()
                else:
                    aviso("err", "Código y nombre son obligatorios y el código no puede repetirse.", icono="alerta")
        elif ss.panel == "entrada":
            seccion("Registrar entrada de mercancía")
            with st.form("f_entrada", border=False):
                cod = st.selectbox("Producto", list(inv.productos), format_func=lambda c: f"{inv.productos[c].nombre} · {c}")
                c1, c2, c3 = st.columns(3)
                cant = c1.number_input("Cantidad", min_value=1, step=1)
                costo = c2.number_input("Costo unitario", min_value=0, step=100)
                vence = c3.date_input("Fecha de vencimiento", value=None, min_value=None)
                g = st.form_submit_button("Registrar entrada", type="primary")
            if g:
                try:
                    inv.productos[cod].registrar_entrada(int(cant), float(costo), vence)
                    ss.flash, ss.panel = ("ok", "Lote creado y costo promedio actualizado."), None
                    st.rerun()
                except ErrorNegocio as e:
                    aviso("err", str(e), icono="alerta")
        elif ss.panel == "baja":
            seccion("Dar de baja por vencimiento o daño")
            cod = st.selectbox("Producto", list(inv.productos), key="baja_prod",
                               format_func=lambda c: f"{inv.productos[c].nombre} · {c}")
            lotes = [l for l in inv.productos[cod].lotes if l.cantidad > 0]
            with st.form("f_baja", border=False):
                etiq_lotes = {f"{codigo_lote(l)} · {l.cantidad} un." + (f" · vence {fecha_corta(l.vence)}" if l.vence else ""): l.id
                              for l in lotes}
                lote_sel = st.selectbox("Lote", list(etiq_lotes)) if lotes else None
                lid = etiq_lotes[lote_sel] if lote_sel else None
                c1, c2 = st.columns(2)
                cant = c1.number_input("Cantidad a dar de baja", min_value=1, step=1)
                tipo = c2.selectbox("Motivo", ["Vencimiento", "Daño"])
                detalle = st.text_input("Detalle (opcional)")
                g = st.form_submit_button("Dar de baja", type="primary")
            if g and lid:
                try:
                    inv.dar_de_baja(user, cod, lid, int(cant), f"{tipo}: {detalle}" if detalle.strip() else tipo)
                    ss.flash, ss.panel = ("ok", "Baja registrada como pérdida del período."), None
                    st.rerun()
                except ErrorNegocio as e:
                    aviso("err", str(e), icono="alerta")
        st.button("Cancelar", key="panel_cancel", on_click=cerrar)


# ======================================================== Ventas (HU-04, HU-05, HU-09)
def registrar_venta_cb() -> None:
    cod, cant, credito = ss.v_prod, int(ss.v_cant), ss.v_pago == "Crédito"
    try:
        v = inv.registrar_venta(user, [(cod, cant)], "credito" if credito else "contado",
                                ss.v_cli if credito else None,
                                autoriza=user if (credito and ss.get("v_aut")) else None)
        ss.horas[v.id] = ahora()
        ss.flash = ("ok", f"Venta #{v.id} registrada por {cop(v.total).replace('&#36;', '$')}. Las existencias se descontaron.")
        ss.v_cant, ss.v_aut = 1, False
    except ErrorNegocio as e:
        ss.flash = ("err", str(e))


def pagina_ventas() -> None:
    cabecera("Cada venta cuenta", "Ventas", "Registra lo que vendes, de contado o a crédito.")
    mostrar_flash()
    codigos = list(inv.productos)
    with st.container(border=True, key="card_venta"):
        seccion("Registrar una venta")
        st.markdown('<div class="tc-nota" style="margin-top:-.6rem">Completa los datos antes de guardar.</div>', unsafe_allow_html=True)
        izq, der = st.columns([1.7, 1], gap="large")
        with izq:
            cod = st.selectbox("Producto", codigos, key="v_prod", format_func=lambda c: f"{inv.productos[c].nombre} · {c}")
            p = inv.productos[cod]
            st.markdown(f'<div class="tc-campo">Precio por unidad: {cop(p.precio_venta)} · Disponibles: {esc(uds(p, p.existencias))}</div>',
                        unsafe_allow_html=True)
            cant = int(st.number_input("Cantidad", min_value=1, step=1, key="v_cant"))
            sin_stock = cant > p.existencias
            if sin_stock:
                st.markdown(f'<style>.st-key-v_cant [data-baseweb="input"],.st-key-v_cant [data-baseweb="base-input"],.st-key-v_cant [data-testid="stNumberInputContainer"]{{border-color:#C62828 !important;box-shadow:0 0 0 1px #C62828;}}</style>'
                            f'<div class="tc-campo err">Solo tienes {p.existencias} {"unidades" if UNIDAD.get(p.codigo, "un.") == "un." else UNIDAD[p.codigo]} disponibles.</div>', unsafe_allow_html=True)
            pago = st.radio("Forma de pago", ["Contado", "Crédito"], key="v_pago", horizontal=True)
            credito = pago == "Crédito"
            cli_nombre = st.selectbox("Cliente", list(inv.clientes), key="v_cli", disabled=not credito)
            st.markdown('<div class="tc-campo">Obligatorio para ventas a crédito.</div>', unsafe_allow_html=True)
        total = cant * p.precio_venta
        cli = inv.clientes[cli_nombre] if credito else None
        excede = bool(cli and cli.excede_limite(total))
        with der:
            extra = ""
            if cli:
                extra = (f'<hr><div class="cli"><b>{esc(cli.nombre)}</b><span>Saldo actual: {cop(cli.saldo)}</span>'
                         f'<span>Límite: {cop(cli.limite_credito)}</span></div>')
            st.markdown(h(f'''<div class="tc-resumen"><div class="tit">Resumen de la venta</div>
            <div class="fila"><span>{cant} × {cop(p.precio_venta)}</span><b>{cop(total)}</b></div><hr>
            <div style="font-size:.8rem;color:#6B7280">{"Total a crédito" if credito else "Total"}</div>
            <div class="tot">{cop(total)}</div>{extra}</div>'''), unsafe_allow_html=True)
            if excede:
                aviso("nar", "Supera el límite de crédito",
                      f"El saldo pasaría de {cli.saldo:,.0f} a {cli.saldo + total:,.0f} y el límite es {cli.limite_credito:,.0f}.".replace(",", "."),
                      "alerta")
                if es_dueno:
                    st.checkbox("Autorizar crédito sobre el límite (propietaria)", key="v_aut")
            st.markdown('<div style="height:.4rem"></div>', unsafe_allow_html=True)
            st.button("Registrar venta", key="v_enviar", type="primary", icon=":material/check:",
                      disabled=sin_stock, on_click=registrar_venta_cb, width="stretch")
            st.markdown(f'<div class="tc-nota">{"Corrige la cantidad para registrar la venta." if sin_stock else "Revisa los datos antes de guardar."}</div>',
                        unsafe_allow_html=True)
    if sin_stock:
        aviso("err", "No hay suficientes existencias",
              f"Pediste {cant} unidades y solo hay {p.existencias}. La venta no se ha registrado.", "alerta")

    # ---- historial
    ventas_hoy = [v for v in inv.ventas if v.fecha == hoy()]
    seccion("Historial de ventas")
    st.markdown(h(f'<div class="tc-nota" style="margin-top:-.3rem"><b>Hoy</b> · {hoy().day} de {MESES[hoy().month - 1]} de {hoy().year}'
                  f' · {len(ventas_hoy)} venta{"s" if len(ventas_hoy) != 1 else ""} registrada{"s" if len(ventas_hoy) != 1 else ""}</div>'),
                unsafe_allow_html=True)
    if ventas_hoy:
        filas, clases = [], []
        for v in sorted(ventas_hoy, key=lambda v: ss.horas.get(v.id, datetime.min.replace(tzinfo=COLOMBIA)), reverse=True):
            l = v.lineas[0]
            hora = hora12(ss.horas[v.id]) if v.id in ss.horas else "—"
            filas.append([esc(hora), f"<b>{esc(l.producto.nombre)}</b>" + (f" +{len(v.lineas) - 1}" if len(v.lineas) > 1 else ""),
                          esc(sum(x.cantidad for x in v.lineas)),
                          f'<span class="tc-pago {v.tipo}">{"Contado" if v.tipo == "contado" else "Crédito"}</span>',
                          esc(v.cliente.nombre if v.cliente else "Venta de mostrador"),
                          cop(v.total) + (" · Anulada" if v.anulada else "")])
            clases.append("anulada" if v.anulada else "")
        validas = [v for v in ventas_hoy if not v.anulada]
        c_ = sum(v.total for v in validas if v.tipo == "contado")
        k_ = sum(v.total for v in validas if v.tipo == "credito")
        tabla(["Hora", "Producto", "Cantidad", "Pago", "Cliente", "Total"], filas,
              pie=f"Total de hoy: {cop(c_ + k_)} · Contado: {cop(c_)} · Crédito: {cop(k_)}", derecha=(5,), clases_fila=clases)
    else:
        aviso("info", "Aún no hay ventas registradas hoy.", icono="info")

    if es_dueno and any(not v.anulada for v in ventas_hoy):
        with st.container(border=True, key="card_anular"):
            seccion("Anular una venta")
            st.markdown('<div class="tc-nota" style="margin-top:-.6rem">La venta no se borra: se anula con motivo, '
                        'las existencias vuelven a sus lotes y queda en la bitácora.</div>', unsafe_allow_html=True)
            ops = {v.id: v for v in ventas_hoy if not v.anulada}
            etiquetas = {f"#{i} · {hora12(ss.horas[i]) if i in ss.horas else ''} · {v.lineas[0].producto.nombre} · "
                         f"{v.total:,.0f}".replace(",", "."): i for i, v in ops.items()}
            st.selectbox("Venta", list(etiquetas), key="an_venta")
            motivo = st.text_input("Motivo de la anulación", key="an_motivo")

            def anular():
                try:
                    inv.anular_venta(user, etiquetas[ss.an_venta], ss.an_motivo)
                    ss.flash, ss.an_motivo = ("ok", "Venta anulada y existencias restauradas."), ""
                except ErrorNegocio as e:
                    ss.flash = ("err", str(e))
            st.button("Anular venta", key="an_enviar", on_click=anular)


# ===================================================== Clientes y fiado (HU-06, HU-07)
def registrar_abono_cb() -> None:
    try:
        monto = float(ss.a_val)
        inv.registrar_abono(user, ss.a_cli, monto)
        ss.flash = ("ok", f"Abono de {cop(monto).replace('&#36;', '$')} recibido en {ss.a_medio.lower()}. Se aplicó a la deuda más antigua.")
        ss.a_val = 0
    except ErrorNegocio as e:
        ss.flash = ("err", str(e))


def pagina_clientes() -> None:
    cabecera("Las cuentas claras", "Clientes y fiado", "Mira quién te debe y registra cada abono, por pequeño que sea.")
    mostrar_flash()
    cls = list(inv.clientes.values())
    con_saldo = [c for c in cls if c.saldo > 0]
    por_cobrar = sum(c.saldo for c in cls)
    vencida = sum(c.deuda_vencida() for c in cls)
    n_venc = sum(1 for c in cls if c.deuda_vencida() > 0)
    n_exc = sum(1 for c in cls if c.saldo > c.limite_credito)
    k1, k2, k3 = st.columns(3)
    k1.markdown(kpi("Total por cobrar", cop(por_cobrar), f"Saldo de {len(con_saldo)} clientes", "gris", "billete"), unsafe_allow_html=True)
    k2.markdown(kpi("Cartera vencida", cop(vencida), f"{n_venc} cliente{'s' if n_venc != 1 else ''} con pagos pendientes",
                    "rojo" if vencida else "verde", "alerta"), unsafe_allow_html=True)
    k3.markdown(kpi("Clientes con fiado", f"{len(con_saldo)} clientes",
                    "Todos dentro de su límite" if not n_exc else f"{n_exc} superan su límite",
                    "verde" if not n_exc else "naranja", "gente"), unsafe_allow_html=True)

    seccion("Cuentas de clientes", f"{len(cls)} clientes")
    tabla(["Cliente", "Límite", "Saldo", "Vencida"],
          [[f"<b>{esc(c.nombre)}</b>", cop(c.limite_credito), cop(c.saldo),
            f'<span class="tono-rojo">{cop(c.deuda_vencida())}</span>' if c.deuda_vencida() else '<span class="tono-gris">&#36;0</span>']
           for c in cls],
          pie="Vencida: parte del saldo con más de 30 días sin pagar. No se suma otra vez al saldo.")

    with st.container(border=True, key="card_abono"):
        seccion("Registrar abono")
        st.markdown('<div class="tc-nota" style="margin-top:-.6rem">El abono se descuenta del saldo del cliente.</div>', unsafe_allow_html=True)
        izq, der = st.columns([1.7, 1], gap="large")
        with izq:
            nombre = st.selectbox("Cliente", list(inv.clientes), key="a_cli")
            c = inv.clientes[nombre]
            g1, g2 = st.columns(2)
            monto = float(g1.number_input("Valor del abono", min_value=0, step=1000, key="a_val"))
            g2.text_input("Fecha", value=fecha_media(hoy()).replace(" ", " "), disabled=True, key="a_fecha")
            st.selectbox("Medio de pago", ["Efectivo", "Transferencia", "Nequi"], key="a_medio")
            st.markdown('<div class="tc-campo">Primero se paga la deuda más antigua.</div>', unsafe_allow_html=True)
        invalido = monto <= 0 or monto > c.saldo
        nuevo = c.saldo - monto if not invalido else c.saldo
        with der:
            st.markdown(h(f'''<div class="tc-resumen"><div class="tit">Así queda la cuenta</div>
            <div class="fila"><span>Saldo actual</span><b>{cop(c.saldo)}</b></div>
            <div class="fila" style="margin-top:.4rem"><span>Este abono</span><b>&minus; {cop(monto)}</b></div><hr>
            <div class="fila"><span>Nuevo saldo</span><b style="font-size:1.4rem">{cop(nuevo)}</b></div></div>'''), unsafe_allow_html=True)
            if monto > c.saldo:
                aviso("err", "El abono supera el saldo del cliente.", icono="alerta")
            elif monto > 0 and c.deuda_vencida() > 0:
                aviso("info", f"Este abono también reduce la cartera vencida de {c.nombre.split()[0]}.", icono="info")
            st.markdown('<div style="height:.4rem"></div>', unsafe_allow_html=True)
            st.button("Registrar abono", key="a_enviar", type="primary", icon=":material/check:",
                      disabled=invalido, on_click=registrar_abono_cb, width="stretch")
            st.markdown('<div class="tc-nota">Revisa el valor antes de guardar. El abono aún no está registrado.</div>', unsafe_allow_html=True)

    if es_dueno:
        with st.expander("Agregar cliente"):
            with st.form("f_cliente", border=False):
                n = st.text_input("Nombre del cliente")
                lim = st.number_input("Límite de crédito (cero = sin fiado)", min_value=0, step=10000)
                g = st.form_submit_button("Guardar cliente", type="primary")
            if g:
                if n.strip() and n.strip() not in inv.clientes:
                    inv.agregar_cliente(Cliente(n.strip(), lim))
                    ss.flash = ("ok", f"Cliente {n.strip()} creado.")
                    st.rerun()
                else:
                    aviso("err", "El nombre es obligatorio y no puede repetirse.", icono="alerta")


# ============================================================= Reportes (HU-07, HU-08)
def pagina_reportes() -> None:
    cabecera("Solo para la propietaria", "Reportes", "Entiende cómo va tu negocio y qué cuentas debes cuidar.")
    try:
        inv.reporte_utilidad(user)  # RN-04 / CP-13: solo el propietario
    except PermisoDenegado as e:
        aviso("err", str(e), icono="alerta")
        return
    d = hoy()
    periodos = {f"Este mes · 1 al {d.day} de {MESES[d.month - 1]} de {d.year}": date(d.year, d.month, 1),
                f"Últimos 7 días": d - timedelta(days=6), "Hoy": d, "Todo el historial": date.min}
    p1, p2 = st.columns([3, 1])
    nombre_p = p1.selectbox("Período", list(periodos), key="periodo")
    desde = periodos[nombre_p]
    validas = [v for v in inv.ventas if not v.anulada and v.fecha >= desde]
    ventas = sum(v.total for v in validas)
    utilidad = sum(v.utilidad for v in validas)
    costo = ventas - utilidad
    perd = [x for x in inv.perdidas if x["fecha"] >= desde]
    p_venc = sum(x["valor"] for x in perd if x["motivo"].lower().startswith("vencimiento"))
    p_dano = sum(x["valor"] for x in perd) - p_venc
    perdidas = p_venc + p_dano

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerows([["TiendaControl", TIENDA], ["Período", nombre_p], [], ["Concepto", "Valor (COP)"], ["Ventas", round(ventas)],
                 ["Costo de la mercancía vendida", round(costo)], ["Utilidad", round(utilidad)],
                 ["Pérdidas por vencimiento", round(p_venc)], ["Pérdidas por daño", round(p_dano)],
                 ["Utilidad después de pérdidas", round(utilidad - perdidas)],
                 ["Saldo por cobrar", round(sum(c.saldo for c in inv.clientes.values()))]])
    p2.markdown("<div style='height:1.65rem'></div>", unsafe_allow_html=True)
    p2.download_button("Descargar reporte", buf.getvalue().encode("utf-8-sig"), file_name=f"reporte_{d.isoformat()}.csv",
                       mime="text/csv", icon=":material/download:", width="stretch")

    k1, k2, k3 = st.columns(3)
    k1.markdown(kpi("Ventas", cop(ventas), "Contado y crédito del período", "gris", "billete"), unsafe_allow_html=True)
    k2.markdown(kpi("Utilidad", cop(utilidad), "Ventas menos costo de mercancía", "verde", "tendencia"), unsafe_allow_html=True)
    k3.markdown(kpi("Pérdidas", cop(perdidas), "Mercancía dada de baja, al costo", "rojo" if perdidas else "gris", "alerta"),
                unsafe_allow_html=True)

    seccion("Tus números, sin enredos")
    st.markdown(h(f'''<div class="tc-card tc-stats">
    <div><div class="t">Costo de la mercancía vendida</div><div class="v">{cop(costo)}</div></div>
    <div><div class="t">Pérdidas por vencimiento / daño</div><div class="v">{cop(p_venc)} / {cop(p_dano)}</div></div>
    <div><div class="t">Utilidad después de pérdidas</div><div class="v">{cop(utilidad - perdidas)}</div></div></div>'''),
                unsafe_allow_html=True)

    # ---- antigüedad de cartera (RN-09)
    rangos = ["0 a 30 días", "31 a 60 días", "Más de 60 días"]
    nombres = ["0–30 días", "31–60 días", "Más de 60 días"]
    saldo = {r: 0.0 for r in rangos}
    cuenta = {r: 0 for r in rangos}
    for c in inv.clientes.values():
        for r, v in c.antiguedad().items():
            if v > 0:
                saldo[r] += v
                cuenta[r] += 1
    total = sum(saldo.values())
    seccion("Antigüedad de cartera")
    st.markdown(h(f'<div class="tc-nota" style="margin-top:-.3rem"><b style="font-size:1.3rem;color:#1B261D">{cop(total)}</b><br>'
                  f'Saldo por cobrar al {d.day} de {MESES[d.month - 1]}. Los días se cuentan desde la venta a crédito.</div>'),
                unsafe_allow_html=True)
    tabla(["Antigüedad", "Clientes", "Saldo por cobrar", "Del total"],
          [[f"<b>{nombres[i]}</b>", f"{cuenta[r]} cliente{'s' if cuenta[r] != 1 else ''}", cop(saldo[r]),
            f"{(saldo[r] / total * 100 if total else 0):.0f}%"] for i, r in enumerate(rangos)],
          pie=f"Total por cobrar: {cop(total)} · Un cliente puede tener deudas en varios rangos.")

    viejas = [(c, [x for x in c.deudas if x.pendiente > 0 and (d - x.fecha).days > 60]) for c in inv.clientes.values()]
    viejas = [(c, sum(x.pendiente for x in ds)) for c, ds in viejas if ds]
    seccion("Empieza por las cuentas más antiguas")
    if viejas:
        c, v = max(viejas, key=lambda t: t[1])
        aviso("nar", f"{c.nombre} tiene {cop(v).replace('&#36;', '$')} con más de 60 días.",
              "Acuerda un abono para recuperar ese dinero.", "alerta")
    else:
        aviso("ok", "No tienes deudas con más de 60 días.", icono="info")


# ===================================================================== Bitácora
def pagina_bitacora() -> None:
    cabecera("Registro de acciones", "Bitácora", "Cada movimiento queda con usuario, fecha y detalle. Nada se borra.")
    mostrar_flash()
    if inv.bitacora:
        tabla(["Fecha", "Usuario", "Acción"], [[esc(f.split(" | ")[0]), esc(f.split(" | ")[1]), esc(f.split(" | ")[2])]
                                                for f in reversed(inv.bitacora)])
    else:
        aviso("info", "Sin movimientos todavía.", icono="info")


# ======================================================================== Router
PAGINA_ACTUAL = {"alertas": pagina_alertas, "inventario": pagina_inventario, "ventas": pagina_ventas,
                 "clientes": pagina_clientes, "reportes": pagina_reportes, "bitacora": pagina_bitacora}[ss.page]
PAGINA_ACTUAL()
st.markdown(h('<div class="tc-nota" style="text-align:center;margin-top:2rem">TiendaControl · Hecho para tu día a día · '
              'Todos los valores en pesos colombianos</div>'), unsafe_allow_html=True)
