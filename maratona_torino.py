import base64
import hmac
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

BASE_DIR = Path(__file__).resolve().parent
IMG_DIR = BASE_DIR / "immagini"
PRIV_DOC_DIR = BASE_DIR / "documenti_privati"
DATA_FILE = BASE_DIR / "postazioni.json"
RISORSE_FILE = BASE_DIR / "risorse_manifestazione.json"
PRIV_DOCUMENTI_FILE = BASE_DIR / "documenti_privati.json"
ETICHETTE_FILE = BASE_DIR / "etichette.json"

IMG_DIR.mkdir(exist_ok=True)
PRIV_DOC_DIR.mkdir(exist_ok=True)


def get_password_area_riservata() -> str:
    """Legge la password da st.secrets su web, con fallback locale per chiavetta USB."""
    try:
        pwd = st.secrets.get("PASSWORD_AREA_RISERVATA", "")
        if isinstance(pwd, str) and pwd.strip():
            return pwd.strip()
    except Exception:
        pass
    return ""


FONT_OPZIONI = {
    "Predefinito (Sistema)": "inherit",
    "Sans-Serif pulito (Arial / Helvetica)": "Arial, Helvetica, sans-serif",
    "Moderno leggibile (Verdana / Tahoma)": "Verdana, Geneva, sans-serif",
    "Classico con grazie (Georgia / Times)": "Georgia, 'Times New Roman', serif",
    "Monospazio tecnico (Courier / Consolas)": "'Courier New', Courier, monospace",
}

STILE_TESTO_OPZIONI = {
    "Normale": ("normal", "400"),
    "Grassetto": ("normal", "700"),
    "Corsivo": ("italic", "400"),
    "Grassetto + Corsivo": ("italic", "700"),
}

ETICHETTE_DEFAULT = {
    "titolo_home": "Turin Marathon 2026 — Postazioni & Incroci",
    "sottotitolo_home": "Consulta la mappa generale del percorso, le risorse della manifestazione e i dettagli delle postazioni.",
    "expander_mappa": "Mappa Generale del Percorso",
    "expander_risorse": "Link & Immagini della Manifestazione",
    "etichetta_ricerca": "Cerca incrocio, ID, radio o personale",
    "titolo_postazioni": "Postazioni Attive",
    "campo_id": "Codice Postazione",
    "campo_nome": "Nome Incrocio",
    "campo_radio": "Codice radio",
    "campo_personale": "Personale assegnato",
    "campo_commenti": "Commenti",
    "stile_titolo_font": "Predefinito (Sistema)",
    "stile_titolo_size": 32,
    "stile_titolo_colore": "#111827",
    "stile_titolo_peso": "Grassetto",
    "stile_sottotitolo_font": "Predefinito (Sistema)",
    "stile_sottotitolo_size": 18,
    "stile_sottotitolo_colore": "#1e3a5f",
    "stile_sottotitolo_peso": "Normale",
    "stile_etichette_font": "Predefinito (Sistema)",
    "stile_etichette_size": 16,
    "stile_etichette_colore": "#111827",
    "stile_etichette_peso": "Grassetto",
    "stile_contenuti_font": "Predefinito (Sistema)",
    "stile_contenuti_size": 15,
    "stile_contenuti_colore": "#1f2937",
    "stile_contenuti_peso": "Normale",
}

st.set_page_config(
    page_title="Turin Marathon 2026 - Gestione Postazioni",
    layout="wide",
)

# --- GESTIONE STATI ---
if "autenticato" not in st.session_state:
    st.session_state.autenticato = False

if "pagina" not in st.session_state:
    st.session_state.pagina = "home"

if "postazione_selezionata" not in st.session_state:
    st.session_state.postazione_selezionata = None

if "img_espanse" not in st.session_state:
    st.session_state.img_espanse = set()


def carica_postazioni() -> list[dict]:
    if not DATA_FILE.exists():
        return []
    with DATA_FILE.open("r", encoding="utf-8") as f:
        dati = json.load(f)
    if not isinstance(dati, list):
        return []
    return dati


def salva_postazioni(lista: list[dict]) -> None:
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(lista, f, indent=2, ensure_ascii=False)


def carica_risorse() -> dict:
    default = {"link": [], "immagini": []}
    if not RISORSE_FILE.exists():
        return default
    with RISORSE_FILE.open("r", encoding="utf-8") as f:
        dati = json.load(f)
    if not isinstance(dati, dict):
        return default
    if not isinstance(dati.get("link"), list):
        dati["link"] = []
    if not isinstance(dati.get("immagini"), list):
        dati["immagini"] = []
    return dati


def salva_risorse(dati: dict) -> None:
    with RISORSE_FILE.open("w", encoding="utf-8") as f:
        json.dump(dati, f, indent=2, ensure_ascii=False)


def carica_documenti_privati() -> list[dict]:
    if not PRIV_DOCUMENTI_FILE.exists():
        return []
    with PRIV_DOCUMENTI_FILE.open("r", encoding="utf-8") as f:
        dati = json.load(f)
    if not isinstance(dati, list):
        return []
    return dati


def salva_documenti_privati(lista: list[dict]) -> None:
    with PRIV_DOCUMENTI_FILE.open("w", encoding="utf-8") as f:
        json.dump(lista, f, indent=2, ensure_ascii=False)


def carica_etichette() -> dict:
    copia = dict(ETICHETTE_DEFAULT)
    if not ETICHETTE_FILE.exists():
        return copia
    with ETICHETTE_FILE.open("r", encoding="utf-8") as f:
        dati = json.load(f)
    if isinstance(dati, dict):
        for chiave, default_val in ETICHETTE_DEFAULT.items():
            val = dati.get(chiave)
            if isinstance(default_val, int):
                if isinstance(val, int) and 10 <= val <= 64:
                    copia[chiave] = val
            elif isinstance(val, str) and val.strip():
                copia[chiave] = val.strip()
    return copia


def salva_etichette(dati: dict) -> None:
    with ETICHETTE_FILE.open("w", encoding="utf-8") as f:
        json.dump(dati, f, indent=2, ensure_ascii=False)


def url_sicuro(url: str) -> str:
    pulito = url.strip()
    parsed = urllib.parse.urlparse(pulito)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return pulito
    return ""


def scarica_immagine_web(url: str, titolo: str = "") -> str:
    url_valido = url_sicuro(url)
    if not url_valido:
        raise ValueError("Inserisci un indirizzo web valido che inizi con http:// o https://")

    parsed = urllib.parse.urlparse(url_valido)
    est = Path(parsed.path).suffix.lower()
    if est not in (".jpg", ".jpeg", ".png", ".webp"):
        est = ".jpg"

    base_nome = re.sub(r"[^a-zA-Z0-9_-]+", "_", (titolo.strip() or Path(parsed.path).stem or "web_img")).strip("_")
    if not base_nome:
        base_nome = "web_img"

    nome_file = f"{base_nome}{est}"
    destinazione = IMG_DIR / nome_file

    req = urllib.request.Request(
        url_valido,
        headers={"User-Agent": "Mozilla/5.0 TurinMarathon2026App/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        contenuto = resp.read()
    if not contenuto:
        raise ValueError("Il file scaricato risulta vuoto.")

    destinazione.write_bytes(contenuto)
    return nome_file


def verifica_password(inserita: str, corretta: str) -> bool:
    return hmac.compare_digest(inserita.encode("utf-8"), corretta.encode("utf-8"))


def estrai_immagini(postazione: dict) -> list[str]:
    risultato: list[str] = []
    if isinstance(postazione.get("immagini"), list):
        for item in postazione["immagini"]:
            if isinstance(item, str) and item.strip():
                risultato.append(item.strip())
    singola = postazione.get("immagine")
    if isinstance(singola, str) and singola.strip() and singola.strip() not in risultato:
        risultato.append(singola.strip())
    return risultato


def salva_file_upload(uploaded_file, cartella: Path = IMG_DIR) -> str:
    nome_pulito = Path(uploaded_file.name).name
    destinazione = cartella / nome_pulito
    destinazione.write_bytes(uploaded_file.getbuffer())
    return nome_pulito


def estrai_testo_docx(percorso: Path) -> str:
    if DocxDocument is None:
        return "Per leggere i file Word (.docx) a schermo installa il pacchetto python-docx (`pip install python-docx`)."
    doc = DocxDocument(str(percorso))
    righe: list[str] = []
    for p in doc.paragraphs:
        if p.text.strip():
            righe.append(p.text.strip())
    for tabella in doc.tables:
        for riga in tabella.rows:
            celle = [c.text.strip() for c in riga.cells if c.text.strip()]
            if celle:
                righe.append(" | ".join(celle))
    return "\n\n".join(righe) if righe else "Il documento Word non contiene testo leggibile."


def mostra_pdf_a_schermo(percorso: Path, idx: int):
    """Mostra il PDF a schermo tramite pdf.js senza installare pacchetti sulla chiavetta."""
    b64_pdf = base64.b64encode(percorso.read_bytes()).decode("utf-8")
    html_viewer = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        body {{ margin: 0; background: #e5eef5; font-family: Arial, sans-serif; text-align: center; }}
        #pdf-container {{ padding: 10px; }}
        canvas.pdf-page {{
          display: block;
          margin: 12px auto;
          max-width: 100%;
          height: auto !important;
          box-shadow: 0 2px 8px rgba(0,0,0,0.18);
          background: #fff;
        }}
        #stato-pdf {{ padding: 14px; color: #111827; font-size: 14px; }}
      </style>
    </head>
    <body>
      <div id="stato-pdf">Caricamento anteprima PDF...</div>
      <div id="pdf-container"></div>
      <script type="module">
        import * as pdfjsLib from 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/pdf.min.mjs';
        pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/pdf.worker.min.mjs';

        const raw = atob("{b64_pdf}");
        const bytes = new Uint8Array(raw.length);
        for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);

        const stato = document.getElementById("stato-pdf");
        const container = document.getElementById("pdf-container");

        try {{
          const pdf = await pdfjsLib.getDocument({{ data: bytes }}).promise;
          stato.textContent = "Pagine PDF: " + pdf.numPages;
          for (let p = 1; p <= pdf.numPages; p++) {{
            const page = await pdf.getPage(p);
            const viewport = page.getViewport({{ scale: 1.4 }});
            const canvas = document.createElement("canvas");
            canvas.className = "pdf-page";
            canvas.width = viewport.width;
            canvas.height = viewport.height;
            container.appendChild(canvas);
            await page.render({{ canvasContext: canvas.getContext("2d"), viewport }}).promise;
          }}
        }} catch (err) {{
          stato.textContent = "Anteprima PDF non disponibile (verifica la connessione o usa un'immagine JPG/PNG del documento).";
        }}
      </script>
    </body>
    </html>
    """
    components.html(html_viewer, height=740, scrolling=True)


def render_documento_privato(doc_info: dict, idx: int):
    nome_file = doc_info.get("file", "")
    percorso = PRIV_DOC_DIR / nome_file

    if not nome_file or not percorso.exists():
        st.warning(f"File non trovato: `{nome_file}`")
        return

    est = percorso.suffix.lower()

    if est == ".pdf":
        mostra_pdf_a_schermo(percorso, idx=idx)

    elif est in (".xlsx", ".xls", ".csv"):
        try:
            if est == ".csv":
                df = pd.read_csv(percorso)
            else:
                xl = pd.ExcelFile(percorso)
                fogli = xl.sheet_names
                foglio_scelto = (
                    st.selectbox(
                        "Seleziona foglio",
                        fogli,
                        key=f"sheet_priv_{idx}_{nome_file}",
                    )
                    if len(fogli) > 1
                    else fogli[0]
                )
                df = pd.read_excel(percorso, sheet_name=foglio_scelto)
            st.dataframe(df, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(f"Impossibile leggere il foglio: {exc}")

    elif est == ".docx":
        testo_doc = estrai_testo_docx(percorso)
        st.markdown(testo_doc.replace("\n\n", "<br><br>"), unsafe_allow_html=True)

    else:
        st.info("Formato non supportato per la visualizzazione a schermo.")


def estrai_lista_personale(testo_personale: str) -> list[str]:
    if not testo_personale or not testo_personale.strip():
        return []
    parti = re.split(
        r"(?:\r?\n+|[,;/]+|\s+\bio\b\s+|\s+\be\b\s+)",
        testo_personale.strip(),
        flags=re.IGNORECASE,
    )
    return [p.strip() for p in parti if p and p.strip()]


def chiave_ordinamento_postazione(postazione: dict):
    """Ordina prima per codice (id) e poi per nome postazione, con numeri in ordine crescente."""
    id_raw = str(postazione.get("id", "")).strip().lower()
    nome_raw = str(postazione.get("nome", "")).strip().lower()
    parti_id = [
        int(p) if p.isdigit() else p
        for p in re.split(r"(\d+)", id_raw)
        if p
    ]
    parti_nome = [
        int(p) if p.isdigit() else p
        for p in re.split(r"(\d+)", nome_raw)
        if p
    ]
    return (
        0 if id_raw else 1,
        parti_id,
        0 if nome_raw else 1,
        parti_nome,
    )


def mostra_immagine_espandibile(
    img_path: Path,
    chiave_univoca: str,
    width_compatta: int = 200,
    is_mappa: bool = False,
    mostra_bottone: bool = True,
):
    if not img_path.exists():
        st.warning(f"Immagine non trovata: `{img_path.name}`")
        return

    espansa = mostra_bottone and (chiave_univoca in st.session_state.img_espanse)

    if is_mappa:
        classe_css = "mappa-espansa" if espansa else "mappa-compatta"
    else:
        classe_css = "img-espansa" if espansa else "img-compatta"

    st.markdown(f'<div class="{classe_css}">', unsafe_allow_html=True)
    st.image(str(img_path), use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if mostra_bottone:
        etichetta_btn = "↩️ Riduci" if espansa else "🔍 Espandi"
        if st.button(etichetta_btn, key=f"btn_zoom_{chiave_univoca}"):
            if espansa:
                st.session_state.img_espanse.discard(chiave_univoca)
            else:
                st.session_state.img_espanse.add(chiave_univoca)
            st.rerun()


def trova_postazione_da_chiave(chiave: str | None, elenco: list[dict]) -> dict | None:
    if not chiave:
        return None
    for p in elenco:
        id_v = str(p.get("id", "")).strip()
        nome_v = str(p.get("nome", "")).strip()
        if f"{id_v}||{nome_v}" == chiave:
            return p
    return None


# --- FINESTRA MODALE AREA RISERVATA ---
@st.dialog("Area Riservata")
def apri_dialog_login():
    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 12px;">
            <div style="
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 64px;
                height: 64px;
                border-radius: 50%;
                background: radial-gradient(circle, #1e293b 0%, #0f172a 100%);
                border: 2px solid #7f1d1d;
                font-size: 30px;
                margin-bottom: 10px;
            ">💡</div>
            <h4 style="margin: 0; color: #0f172a; font-weight: 700;">
                Inserisci la password per gestire postazioni e incroci
            </h4>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("form_login_modale"):
        pwd = st.text_input("Password", type="password", placeholder="••••••••")
        accedi = st.form_submit_button("🔒 Accedi alla Gestione", use_container_width=True)

        if accedi:
            if verifica_password(pwd, get_password_area_riservata()):
                st.session_state.autenticato = True
                st.session_state.postazione_selezionata = None
                st.session_state.pagina = "gestione"
                st.rerun()
            else:
                st.error("Password non corretta.")


postazioni = carica_postazioni()
risorse = carica_risorse()
documenti_privati = carica_documenti_privati()
etichette = carica_etichette()

# --- COSTRUZIONE VARIABILI CSS DAI PARAMETRI SALVATI ---
t_font = FONT_OPZIONI.get(etichette["stile_titolo_font"], "inherit")
t_size = etichette["stile_titolo_size"]
t_col = etichette["stile_titolo_colore"]
t_style, t_weight = STILE_TESTO_OPZIONI.get(etichette["stile_titolo_peso"], ("normal", "700"))

s_font = FONT_OPZIONI.get(etichette["stile_sottotitolo_font"], "inherit")
s_size = etichette["stile_sottotitolo_size"]
s_col = etichette["stile_sottotitolo_colore"]
s_style, s_weight = STILE_TESTO_OPZIONI.get(etichette["stile_sottotitolo_peso"], ("normal", "400"))

e_font = FONT_OPZIONI.get(etichette["stile_etichette_font"], "inherit")
e_size = etichette["stile_etichette_size"]
e_col = etichette["stile_etichette_colore"]
e_style, e_weight = STILE_TESTO_OPZIONI.get(etichette["stile_etichette_peso"], ("normal", "700"))

c_font = FONT_OPZIONI.get(etichette["stile_contenuti_font"], "inherit")
c_size = etichette["stile_contenuti_size"]
c_col = etichette["stile_contenuti_colore"]
c_style, c_weight = STILE_TESTO_OPZIONI.get(etichette["stile_contenuti_peso"], ("normal", "400"))

# --- STILE CSS DINAMICO ---
st.markdown(
    f"""
    <style>
    /* Sfondo azzurrino tenue riposante per la lettura */
    [data-testid="stAppViewContainer"] {{
        background: linear-gradient(180deg, #eaf4fb 0%, #dcebf7 100%) !important;
        color: #111827 !important;
    }}

    /* Forza colore scuro leggibile sui testi standard anche con tema scuro su cellulare/tablet */
    [data-testid="stAppViewContainer"] h1,
    [data-testid="stAppViewContainer"] h2,
    [data-testid="stAppViewContainer"] h3,
    [data-testid="stAppViewContainer"] h4,
    [data-testid="stAppViewContainer"] p,
    [data-testid="stAppViewContainer"] label,
    [data-testid="stAppViewContainer"] .stMarkdown,
    [data-testid="stAppViewContainer"] .stMarkdown p,
    [data-testid="stAppViewContainer"] .stMarkdown li,
    [data-testid="stAppViewContainer"] [data-testid="stCaptionContainer"],
    [data-testid="stAppViewContainer"] [data-testid="stCaptionContainer"] *,
    [data-testid="stAppViewContainer"] [data-testid="stExpander"] summary,
    [data-testid="stAppViewContainer"] [data-testid="stExpander"] summary * {{
        color: #111827 !important;
    }}

    /* --- STILI PERSONALIZZATI DALL'AREA RISERVATA --- */
    .titolo-home-custom {{
        font-family: {t_font} !important;
        font-size: {t_size}px !important;
        color: {t_col} !important;
        font-style: {t_style} !important;
        font-weight: {t_weight} !important;
        line-height: 1.2 !important;
        margin: 0.2rem 0 0.45rem 0 !important;
    }}

    .sottotitolo-home-custom {{
        font-family: {s_font} !important;
        font-size: {s_size}px !important;
        color: {s_col} !important;
        font-style: {s_style} !important;
        font-weight: {s_weight} !important;
        line-height: 1.4 !important;
        margin: 0 0 0.9rem 0 !important;
    }}

    /* Intestazioni tendine, ricerca e titoli sezione */
    [data-testid="stAppViewContainer"] [data-testid="stExpander"] summary p,
    [data-testid="stAppViewContainer"] [data-testid="stTextInput"] label p,
    .intestazione-sezione-custom {{
        font-family: {e_font} !important;
        font-size: {e_size}px !important;
        color: {e_col} !important;
        font-style: {e_style} !important;
        font-weight: {e_weight} !important;
    }}

    .etichetta-campo-custom {{
        font-family: {e_font} !important;
        font-size: {e_size}px !important;
        color: {e_col} !important;
        font-style: {e_style} !important;
        font-weight: {e_weight} !important;
    }}

    /* Campi di testo e aree di testo leggibili su cellulare e tablet */
    [data-testid="stAppViewContainer"] input,
    [data-testid="stAppViewContainer"] textarea {{
        color: #111827 !important;
        background-color: #ffffff !important;
    }}
    [data-testid="stAppViewContainer"] input::placeholder,
    [data-testid="stAppViewContainer"] textarea::placeholder {{
        color: #6b7280 !important;
        opacity: 1 !important;
    }}

    /* Pulsanti blu scuro a pillola (Torna alla Home / Logout / Area Riservata) */
    div[data-testid="stButton"] > button[kind="primary"],
    div[data-testid="stButton"] > button[kind="primary"] * {{
        background-color: #142143 !important;
        color: #ffffff !important;
        border: 2px solid #3b1d36 !important;
        border-radius: 50px !important;
        padding: 0.5rem 1.4rem !important;
        font-weight: 600 !important;
        font-size: 0.98rem !important;
        transition: all 0.2s ease-in-out;
    }}
    div[data-testid="stButton"] > button[kind="primary"]:hover {{
        background-color: #1e3263 !important;
        border-color: #5c2d54 !important;
    }}

    /* Pulsante "Pubblica" bianco largo nei form */
    div[data-testid="stFormSubmitButton"] > button[kind="primary"] {{
        background-color: #ffffff !important;
        color: #1f2937 !important;
        border: 1px solid #d1d5db !important;
        border-radius: 8px !important;
        padding: 0.5rem 1rem !important;
        font-weight: 600 !important;
        width: 100% !important;
    }}
    div[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {{
        background-color: #f3f4f6 !important;
        border-color: #9ca3af !important;
    }}

    /* Riquadri schede (st.container(border=True)) */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        max-width: 100% !important;
        background-color: #f8fcff !important;
    }}
    div[data-testid="stVerticalBlockBorderWrapper"] > div {{
        padding: 0.75rem 0.85rem !important;
    }}

    /* Compatta la distanza tra gli elementi dentro i riquadri */
    div[data-testid="stVerticalBlockBorderWrapper"] .element-container {{
        margin-bottom: 0.25rem !important;
    }}

    /* Pulsante Espandi / Riduci immagine */
    div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stButton"] > button {{
        padding: 0.3rem 0.75rem !important;
        font-size: 0.85rem !important;
        min-height: 0 !important;
    }}

    /* Immagini grandi sulla Home per una lettura chiara già al primo sguardo */
    div[data-testid="stImage"].img-compatta img {{
        width: 100% !important;
        max-height: 290px !important;
        object-fit: contain !important;
        border-radius: 6px !important;
    }}

    /* Immagini espanse per il massimo dettaglio */
    div[data-testid="stImage"].img-espansa img {{
        width: 100% !important;
        max-height: none !important;
        object-fit: contain !important;
        border-radius: 8px !important;
    }}

    /* Piantina generale ampia e leggibile su cellulare e tablet */
    div[data-testid="stImage"].mappa-compatta img {{
        width: 100% !important;
        max-height: 360px !important;
        object-fit: contain !important;
        border-radius: 6px !important;
    }}

    div[data-testid="stImage"].mappa-espansa img {{
        width: 100% !important;
        max-height: none !important;
        object-fit: contain !important;
        border-radius: 8px !important;
    }}

    /* Testo nelle schede postazione */
    .scheda-titolo {{
        font-family: {e_font} !important;
        font-size: {max(e_size + 1, 16)}px !important;
        font-weight: 700 !important;
        margin: 0 0 0.35rem 0;
        line-height: 1.25;
        color: {e_col} !important;
    }}
    .scheda-riga {{
        font-family: {c_font} !important;
        font-size: {c_size}px !important;
        font-style: {c_style} !important;
        font-weight: {c_weight} !important;
        line-height: 1.35;
        margin: 0.25rem 0;
        color: {c_col} !important;
    }}
    .lista-personale {{
        margin: 0.08rem 0 0.25rem 1.15rem;
        padding: 0;
        font-family: {c_font} !important;
        font-size: {c_size}px !important;
        font-style: {c_style} !important;
        font-weight: {c_weight} !important;
        line-height: 1.32;
        color: {c_col} !important;
    }}
    .lista-personale li {{
        margin-bottom: 0.08rem;
    }}

    /* Dettaglio postazione a pagina singola: testi ben leggibili su cellulare e tablet */
    .dettaglio-titolo {{
        font-family: {t_font} !important;
        font-size: {max(t_size - 4, 22)}px !important;
        font-weight: 700 !important;
        margin: 0 0 0.5rem 0;
        line-height: 1.25;
        color: {t_col} !important;
    }}
    .dettaglio-riga {{
        font-family: {c_font} !important;
        font-size: {c_size + 2}px !important;
        font-style: {c_style} !important;
        font-weight: {c_weight} !important;
        line-height: 1.45;
        margin: 0.45rem 0;
        color: {c_col} !important;
    }}
    .dettaglio-lista {{
        margin: 0.2rem 0 0.5rem 1.25rem;
        padding: 0;
        font-family: {c_font} !important;
        font-size: {c_size + 2}px !important;
        font-style: {c_style} !important;
        font-weight: {c_weight} !important;
        line-height: 1.4;
        color: {c_col} !important;
    }}
    .dettaglio-lista li {{
        margin-bottom: 0.15rem;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ==============================================================================
# BARRA SUPERIORE
# ==============================================================================
if st.session_state.pagina == "gestione" and st.session_state.autenticato:
    c_home, c_logout = st.columns(2)
    with c_home:
        if st.button("🏠 Torna alla Home", type="primary", use_container_width=True):
            st.session_state.postazione_selezionata = None
            st.session_state.pagina = "home"
            st.rerun()
    with c_logout:
        if st.button("🚪 Logout", type="primary", use_container_width=True):
            st.session_state.autenticato = False
            st.session_state.postazione_selezionata = None
            st.session_state.pagina = "home"
            st.rerun()
else:
    c_spazio, c_riservata = st.columns([3, 1])
    with c_riservata:
        if st.session_state.autenticato:
            if st.button("⚙️ Gestione Postazioni", type="primary", use_container_width=True):
                st.session_state.postazione_selezionata = None
                st.session_state.pagina = "gestione"
                st.rerun()
        else:
            if st.button("🔒 Area Riservata", type="primary", use_container_width=True):
                apri_dialog_login()

st.divider()

# ==============================================================================
# PAGINA 1: HOME (O SCHEDA SINGOLA POSTAZIONE SELEZIONATA)
# ==============================================================================
if st.session_state.pagina == "home":
    post_dettaglio = trova_postazione_da_chiave(st.session_state.postazione_selezionata, postazioni)

    if post_dettaglio is not None:
        if st.button("⬅️ Torna a tutte le postazioni", type="primary", use_container_width=True):
            st.session_state.postazione_selezionata = None
            st.rerun()

        st.divider()

        id_val = str(post_dettaglio.get("id", "")).strip()
        nome_val = str(post_dettaglio.get("nome", "")).strip()
        intestazione_det = (
            f"{id_val} — {nome_val}"
            if id_val and nome_val
            else (id_val or nome_val or "Dettaglio postazione")
        )

        with st.container(border=True):
            st.markdown(
                f'<div class="dettaglio-titolo">{intestazione_det}</div>',
                unsafe_allow_html=True,
            )

            imgs_det = estrai_immagini(post_dettaglio)
            if imgs_det:
                for img_idx, img_nome in enumerate(imgs_det):
                    img_path = IMG_DIR / img_nome
                    mostra_immagine_espandibile(
                        img_path=img_path,
                        chiave_univoca=f"det_{id_val}_{nome_val}_{img_idx}_{img_nome}",
                        width_compatta=320,
                        mostra_bottone=False,
                    )
            else:
                st.caption("Nessuna foto associata.")

            radio_txt = post_dettaglio.get("codice_radio") or "-"
            commenti_txt = post_dettaglio.get("commenti") or "-"
            nomi_pers = estrai_lista_personale(str(post_dettaglio.get("personale", "")))

            if id_val:
                st.markdown(
                    f'<div class="dettaglio-riga"><span class="etichetta-campo-custom">{etichette["campo_id"]}:</span> {id_val}</div>',
                    unsafe_allow_html=True,
                )
            if nome_val:
                st.markdown(
                    f'<div class="dettaglio-riga"><span class="etichetta-campo-custom">{etichette["campo_nome"]}:</span> {nome_val}</div>',
                    unsafe_allow_html=True,
                )

            st.markdown(
                f'<div class="dettaglio-riga"><span class="etichetta-campo-custom">{etichette["campo_radio"]}:</span> {radio_txt}</div>',
                unsafe_allow_html=True,
            )

            if nomi_pers:
                voci_li = "".join(f"<li>{nome}</li>" for nome in nomi_pers)
                st.markdown(
                    f'<div class="dettaglio-riga"><span class="etichetta-campo-custom">{etichette["campo_personale"]}:</span></div>'
                    f'<ul class="dettaglio-lista">{voci_li}</ul>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="dettaglio-riga"><span class="etichetta-campo-custom">{etichette["campo_personale"]}:</span> -</div>',
                    unsafe_allow_html=True,
                )

            st.markdown(
                f'<div class="dettaglio-riga"><span class="etichetta-campo-custom">{etichette["campo_commenti"]}:</span> {commenti_txt}</div>',
                unsafe_allow_html=True,
            )

    else:
        st.markdown(
            f'<h1 class="titolo-home-custom">{etichette["titolo_home"]}</h1>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="sottotitolo-home-custom">{etichette["sottotitolo_home"]}</div>',
            unsafe_allow_html=True,
        )

        mappa_path = IMG_DIR / "mappa_generale.jpg"

        with st.expander(etichette["expander_mappa"], expanded=False):
            if mappa_path.exists():
                mostra_immagine_espandibile(
                    img_path=mappa_path,
                    chiave_univoca="mappa_generale_home",
                    width_compatta=280,
                    is_mappa=True,
                    mostra_bottone=True,
                )
            else:
                st.warning("Inserisci il file `immagini/mappa_generale.jpg` nella cartella `immagini`.")

        # --- SPAZIO LINK & IMMAGINI DELLA MANIFESTAZIONE ---
        link_lista = risorse.get("link", [])
        img_lista = risorse.get("immagini", [])
        titolo_risorse_exp = f"{etichette['expander_risorse']} ({len(link_lista)} link · {len(img_lista)} immagini)"
        with st.expander(titolo_risorse_exp, expanded=False):
            if not link_lista and not img_lista:
                st.info("Nessun link o immagine della manifestazione inserito. Puoi aggiungerli dall'Area Riservata.")
            else:
                if link_lista:
                    st.markdown("**Link utili della manifestazione**")
                    for item in link_lista:
                        titolo_l = item.get("titolo") or item.get("url", "Link")
                        url_l = url_sicuro(item.get("url", ""))
                        nota_l = item.get("nota", "")
                        if url_l:
                            st.markdown(f"- [{titolo_l}]({url_l})" + (f" — {nota_l}" if nota_l else ""))
                        else:
                            st.markdown(f"- **{titolo_l}**" + (f" — {nota_l}" if nota_l else ""))

                if img_lista:
                    st.markdown("**Immagini della manifestazione**")
                    for inizio_r in range(0, len(img_lista), 3):
                        riga_r = img_lista[inizio_r : inizio_r + 3]
                        cols_r = st.columns(3)
                        for col_r_idx, r_img in enumerate(riga_r):
                            r_idx = inizio_r + col_r_idx
                            with cols_r[col_r_idx]:
                                with st.container(border=True):
                                    nome_r = r_img.get("file", "")
                                    titolo_r = r_img.get("titolo") or ""
                                    if titolo_r:
                                        st.markdown(f"**{titolo_r}**")
                                    mostra_immagine_espandibile(
                                        img_path=IMG_DIR / nome_r,
                                        chiave_univoca=f"risorsa_img_{r_idx}_{nome_r}",
                                        width_compatta=200,
                                        mostra_bottone=False,
                                    )
                                    if r_img.get("fonte_url"):
                                        st.caption(f"Fonte: {r_img['fonte_url']}")

        filtro = st.text_input(etichette["etichetta_ricerca"], "").strip().lower()

        if filtro:
            postazioni_filtrate = [
                p for p in postazioni
                if filtro in str(p.get("id", "")).lower()
                or filtro in str(p.get("nome", "")).lower()
                or filtro in str(p.get("codice_radio", "")).lower()
                or filtro in str(p.get("personale", "")).lower()
                or filtro in str(p.get("commenti", "")).lower()
            ]
        else:
            postazioni_filtrate = postazioni

        postazioni_ordinate = sorted(postazioni_filtrate, key=chiave_ordinamento_postazione)

        st.markdown(
            f'<div class="intestazione-sezione-custom" style="margin: 0.6rem 0;">{etichette["titolo_postazioni"]} ({len(postazioni_ordinate)})</div>',
            unsafe_allow_html=True,
        )

        if not postazioni_ordinate:
            st.info("Nessuna postazione presente. Accedi all'Area Riservata in alto a destra per inserirle.")
        else:
            for inizio in range(0, len(postazioni_ordinate), 3):
                riga_postazioni = postazioni_ordinate[inizio : inizio + 3]
                cols = st.columns(3)
                for col_idx, p in enumerate(riga_postazioni):
                    idx = inizio + col_idx
                    with cols[col_idx]:
                        with st.container(border=True):
                            id_val = str(p.get("id", "")).strip()
                            nome_val = str(p.get("nome", "")).strip()
                            intestazione_card = (
                                f"{id_val} — {nome_val}"
                                if id_val and nome_val
                                else (id_val or nome_val)
                            )

                            st.markdown(
                                f'<div class="scheda-titolo">{intestazione_card}</div>',
                                unsafe_allow_html=True,
                            )

                            if st.button(
                                f"📋 Apri scheda {id_val or nome_val}",
                                key=f"apri_post_{idx}_{id_val}_{nome_val}",
                                use_container_width=True,
                            ):
                                st.session_state.postazione_selezionata = f"{id_val}||{nome_val}"
                                st.rerun()

                            imgs = estrai_immagini(p)
                            if imgs:
                                for img_idx, img_nome in enumerate(imgs):
                                    img_path = IMG_DIR / img_nome
                                    mostra_immagine_espandibile(
                                        img_path=img_path,
                                        chiave_univoca=f"post_{idx}_{img_idx}_{img_nome}",
                                        width_compatta=200,
                                        mostra_bottone=False,
                                    )
                            else:
                                st.caption("Nessuna foto associata.")

                            radio_txt = p.get("codice_radio") or "-"
                            commenti_txt = p.get("commenti") or "-"
                            nomi_pers = estrai_lista_personale(str(p.get("personale", "")))

                            st.markdown(
                                f'<div class="scheda-riga"><span class="etichetta-campo-custom">{etichette["campo_radio"]}:</span> {radio_txt}</div>',
                                unsafe_allow_html=True,
                            )

                            if nomi_pers:
                                voci_li = "".join(f"<li>{nome}</li>" for nome in nomi_pers)
                                st.markdown(
                                    f'<div class="scheda-riga"><span class="etichetta-campo-custom">{etichette["campo_personale"]}:</span></div>'
                                    f'<ul class="lista-personale">{voci_li}</ul>',
                                    unsafe_allow_html=True,
                                )
                            else:
                                st.markdown(
                                    f'<div class="scheda-riga"><span class="etichetta-campo-custom">{etichette["campo_personale"]}:</span> -</div>',
                                    unsafe_allow_html=True,
                                )

                            st.markdown(
                                f'<div class="scheda-riga"><span class="etichetta-campo-custom">{etichette["campo_commenti"]}:</span> {commenti_txt}</div>',
                                unsafe_allow_html=True,
                            )

# ==============================================================================
# PAGINA 2: AREA RISERVATA
# ==============================================================================
elif st.session_state.pagina == "gestione" and st.session_state.autenticato:
    st.title("Area Riservata — Gestione Postazioni")

    azione = st.selectbox(
        "Seleziona l'operazione da eseguire:",
        [
            "➕ Aggiungi nuova postazione",
            "✏️ Modifica una postazione esistente",
            "🗑️ Elimina una postazione",
            "🗺️ Aggiorna Mappa Generale del Percorso",
            "🔐 Documenti Privati (PDF, Excel, Word)",
            "🔗 Gestisci Link & Immagini Manifestazione",
            "🏷️ Personalizza Titoli & Etichette",
        ],
    )

    st.divider()

    # --- OPZIONE 1: AGGIUNGI NUOVA POSTAZIONE ---
    if azione == "➕ Aggiungi nuova postazione":
        st.subheader("Aggiungi nuova postazione")
        with st.form("form_nuova_postazione", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                nuovo_id = st.text_input(f"{etichette['campo_id']} (es. MIKE 49)")
                nuovo_nome = st.text_input(f"{etichette['campo_nome']} (es. Drosso 145)")
                nuovo_radio = st.text_input(etichette["campo_radio"])
            with c2:
                nuovo_personale = st.text_area(
                    f"{etichette['campo_personale']} (un nome per riga o separato da virgola)",
                    height=75,
                )
                nuovi_commenti = st.text_area(f"{etichette['campo_commenti']} / Note operative", height=75)

            foto_caricate = st.file_uploader(
                "Carica una o più foto JPG dell'incrocio",
                type=["jpg", "jpeg"],
                accept_multiple_files=True,
            )
            nomi_file_manuali = st.text_input(
                "Oppure scrivi uno o più nomi file JPG già presenti in 'immagini/' (separati da virgola)"
            )

            pubblica = st.form_submit_button("Pubblica", type="primary", use_container_width=True)

            if pubblica:
                if not nuovo_nome.strip() and not nuovo_id.strip():
                    st.error(f"Inserisci almeno {etichette['campo_id']} o {etichette['campo_nome']}.")
                else:
                    lista_img: list[str] = []
                    if nomi_file_manuali.strip():
                        for parte in nomi_file_manuali.split(","):
                            if parte.strip():
                                lista_img.append(parte.strip())
                    if foto_caricate:
                        for f_up in foto_caricate:
                            salv = salva_file_upload(f_up, IMG_DIR)
                            if salv not in lista_img:
                                lista_img.append(salv)

                    postazioni.append({
                        "id": nuovo_id.strip(),
                        "nome": nuovo_nome.strip(),
                        "immagine": lista_img[0] if lista_img else "",
                        "immagini": lista_img,
                        "codice_radio": nuovo_radio.strip(),
                        "personale": nuovo_personale.strip(),
                        "commenti": nuovi_commenti.strip(),
                    })
                    salva_postazioni(postazioni)
                    st.success("Nuova postazione pubblicata!")
                    st.rerun()

    # --- OPZIONE 2: MODIFICA POSTAZIONE ESISTENTE ---
    elif azione == "✏️ Modifica una postazione esistente":
        st.subheader("Modifica una postazione esistente")
        if not postazioni:
            st.info("Non ci sono ancora postazioni salvate da modificare.")
        else:
            opzioni = [
                f"{i} - {p.get('id', '')} {p.get('nome', '')}".strip()
                for i, p in enumerate(postazioni)
            ]
            scelta = st.selectbox("Seleziona la postazione da modificare", opzioni, key="select_postazione_mod")
            indice = int(scelta.split(" - ", 1)[0])
            corrente = postazioni[indice]
            imgs_correnti = estrai_immagini(corrente)

            with st.form(f"form_modifica_postazione_{indice}"):
                col_sx, col_dx = st.columns(2)

                with col_sx:
                    m_id = st.text_input(etichette["campo_id"], value=str(corrente.get("id", "")))
                    m_nome = st.text_input(etichette["campo_nome"], value=str(corrente.get("nome", "")))
                    m_radio = st.text_input(etichette["campo_radio"], value=str(corrente.get("codice_radio", "")))

                with col_dx:
                    m_personale = st.text_area(
                        etichette["campo_personale"],
                        value=str(corrente.get("personale", "")),
                        height=95,
                    )
                    m_commenti = st.text_area(
                        f"{etichette['campo_commenti']} / Note operative",
                        value=str(corrente.get("commenti", "")),
                        height=95,
                    )

                st.markdown("**Immagini associate alla postazione**")
                m_imgs_testo = st.text_input(
                    "Nomi file JPG in 'immagini/' (separati da virgola se più di uno)",
                    value=", ".join(imgs_correnti),
                )

                imgs_da_rimuovere: list[str] = []
                if imgs_correnti:
                    st.caption("Spunta eventuali immagini da rimuovere:")
                    cols_img = st.columns(min(len(imgs_correnti), 3))
                    for idx_img, nome_img in enumerate(imgs_correnti):
                        with cols_img[idx_img % len(cols_img)]:
                            p_img = IMG_DIR / nome_img
                            if p_img.exists():
                                st.markdown('<div class="img-compatta">', unsafe_allow_html=True)
                                st.image(str(p_img), use_container_width=True)
                                st.markdown("</div>", unsafe_allow_html=True)
                            else:
                                st.warning(f"File non trovato: {nome_img}")
                            if st.checkbox(f"Rimuovi {nome_img}", key=f"rm_{indice}_{idx_img}"):
                                imgs_da_rimuovere.append(nome_img)

                nuove_foto_mod = st.file_uploader(
                    "Carica nuove foto JPG da aggiungere",
                    type=["jpg", "jpeg"],
                    accept_multiple_files=True,
                    key=f"up_mod_{indice}",
                )

                btn_pubblica_mod = st.form_submit_button(
                    "Pubblica modifiche",
                    type="primary",
                    use_container_width=True,
                )

                if btn_pubblica_mod:
                    lista_finale: list[str] = []
                    for parte in m_imgs_testo.split(","):
                        n = parte.strip()
                        if n and n not in imgs_da_rimuovere and n not in lista_finale:
                            lista_finale.append(n)

                    if nuove_foto_mod:
                        for f_up in nuove_foto_mod:
                            salv = salva_file_upload(f_up, IMG_DIR)
                            if salv not in imgs_da_rimuovere and salv not in lista_finale:
                                lista_finale.append(salv)

                    postazioni[indice] = {
                        "id": m_id.strip(),
                        "nome": m_nome.strip(),
                        "immagine": lista_finale[0] if lista_finale else "",
                        "immagini": lista_finale,
                        "codice_radio": m_radio.strip(),
                        "personale": m_personale.strip(),
                        "commenti": m_commenti.strip(),
                    }
                    salva_postazioni(postazioni)
                    st.success("Modifiche salvate e pubblicate!")
                    st.rerun()

    # --- OPZIONE 3: ELIMINA UNA POSTAZIONE ---
    elif azione == "🗑️ Elimina una postazione":
        st.subheader("Elimina una postazione")
        if not postazioni:
            st.info("Non ci sono postazioni da eliminare.")
        else:
            opzioni_del = [
                f"{i} - {p.get('id', '')} {p.get('nome', '')}".strip()
                for i, p in enumerate(postazioni)
            ]
            scelta_del = st.selectbox("Seleziona la postazione da eliminare", opzioni_del, key="select_postazione_del")
            idx_del = int(scelta_del.split(" - ", 1)[0])
            da_eliminare = postazioni[idx_del]

            st.warning(f"Stai per eliminare definitivamente: **{da_eliminare.get('id', '')} — {da_eliminare.get('nome', '')}**")
            with st.form("form_elimina_postazione"):
                conferma_del = st.form_submit_button("Conferma ed elimina", type="primary", use_container_width=True)
                if conferma_del:
                    postazioni.pop(idx_del)
                    salva_postazioni(postazioni)
                    st.success("Postazione eliminata.")
                    st.rerun()

    # --- OPZIONE 4: AGGIORNA MAPPA GENERALE ---
    elif azione == "🗺️ Aggiorna Mappa Generale del Percorso":
        st.subheader("Aggiorna Mappa Generale del Percorso")
        mappa_att = IMG_DIR / "mappa_generale.jpg"
        if mappa_att.exists():
            st.markdown('<div class="mappa-compatta">', unsafe_allow_html=True)
            st.image(str(mappa_att), use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
        with st.form("form_mappa_generale"):
            nuova_mappa = st.file_uploader("Carica nuova mappa generale JPG", type=["jpg", "jpeg"])
            salva_mappa = st.form_submit_button("Pubblica nuova mappa", type="primary", use_container_width=True)
            if salva_mappa and nuova_mappa is not None:
                mappa_att.write_bytes(nuova_mappa.getbuffer())
                st.success("Mappa generale aggiornata!")
                st.rerun()

    # --- OPZIONE 5: DOCUMENTI PRIVATI (SOLO AREA RISERVATA) ---
    elif azione == "🔐 Documenti Privati (PDF, Excel, Word)":
        st.subheader("Documenti Privati (visibili solo a te)")
        if DocxDocument is None:
            st.caption("Suggerimento: per visualizzare anche il testo dei file Word (.docx) a schermo, installa `python-docx`.")

        with st.form("form_aggiungi_doc_privato", clear_on_submit=True):
            dp_titolo = st.text_input("Titolo documento privato (es. Turni Interni / Numeri Emergenza)")
            dp_nota = st.text_input("Nota personale (opzionale)")
            dp_file = st.file_uploader(
                "Carica documento privato (PDF, Excel .xlsx/.csv o Word .docx)",
                type=["pdf", "xlsx", "xls", "csv", "docx"],
            )
            btn_add_priv = st.form_submit_button("Salva documento privato", type="primary", use_container_width=True)

            if btn_add_priv:
                if dp_file is None:
                    st.error("Seleziona un file PDF, Excel o Word da caricare.")
                else:
                    nome_p = salva_file_upload(dp_file, PRIV_DOC_DIR)
                    documenti_privati.append({
                        "titolo": dp_titolo.strip() or nome_p,
                        "file": nome_p,
                        "nota": dp_nota.strip(),
                    })
                    salva_documenti_privati(documenti_privati)
                    st.success(f"Documento privato '{nome_p}' salvato!")
                    st.rerun()

        if documenti_privati:
            st.divider()
            st.markdown("**Consulta o elimina un documento privato**")
            opzioni_priv = [
                f"{i} — {d.get('titolo', d.get('file', 'Documento'))}"
                for i, d in enumerate(documenti_privati)
            ]
            scelta_priv = st.selectbox("Seleziona documento da visualizzare", opzioni_priv, key="sel_doc_priv")
            idx_priv = int(scelta_priv.split(" — ", 1)[0])
            doc_priv_sel = documenti_privati[idx_priv]

            with st.container(border=True):
                st.markdown(
                    f'<div class="dettaglio-titolo">{doc_priv_sel.get("titolo", "Documento")}</div>',
                    unsafe_allow_html=True,
                )
                if doc_priv_sel.get("nota"):
                    st.caption(doc_priv_sel["nota"])
                render_documento_privato(doc_priv_sel, idx=idx_priv)

            if st.button("🗑️ Elimina questo documento privato", key=f"del_priv_{idx_priv}"):
                documenti_privati.pop(idx_priv)
                salva_documenti_privati(documenti_privati)
                st.rerun()
        else:
            st.info("Nessun documento privato salvato al momento.")

    # --- OPZIONE 6: LINK & IMMAGINI DELLA MANIFESTAZIONE ---
    elif azione == "🔗 Gestisci Link & Immagini Manifestazione":
        st.subheader("Link & Immagini della Manifestazione")

        with st.form("form_aggiungi_link_manifestazione", clear_on_submit=True):
            st.markdown("**Aggiungi un link della manifestazione**")
            l_titolo = st.text_input("Titolo link (es. Sito Ufficiale Turin Marathon / Ordinanza traffico)")
            l_url = st.text_input("Indirizzo web (https://...)")
            l_nota = st.text_input("Nota breve (opzionale)")
            btn_add_link = st.form_submit_button("Pubblica link", type="primary", use_container_width=True)

            if btn_add_link:
                valido = url_sicuro(l_url)
                if not valido:
                    st.error("Inserisci un URL valido che inizi con `https://` o `http://`.")
                else:
                    risorse["link"].append({
                        "titolo": l_titolo.strip() or valido,
                        "url": valido,
                        "nota": l_nota.strip(),
                    })
                    salva_risorse(risorse)
                    st.success("Link aggiunto alla manifestazione!")
                    st.rerun()

        st.divider()

        with st.form("form_aggiungi_img_manifestazione", clear_on_submit=True):
            st.markdown("**Aggiungi un'immagine della manifestazione (da link internet o file locale)**")
            r_titolo = st.text_input("Didascalia / Titolo immagine")
            r_url_img = st.text_input("Link diretto all'immagine su internet (opzionale, es. https://.../locandina.jpg)")
            r_file_img = st.file_uploader("Oppure carica un'immagine dal computer", type=["jpg", "jpeg", "png", "webp"])
            btn_add_img = st.form_submit_button("Pubblica immagine", type="primary", use_container_width=True)

            if btn_add_img:
                nome_salv = ""
                fonte_txt = ""
                try:
                    if r_file_img is not None:
                        nome_salv = salva_file_upload(r_file_img, IMG_DIR)
                    elif r_url_img.strip():
                        fonte_txt = url_sicuro(r_url_img)
                        if not fonte_txt:
                            raise ValueError("Inserisci un URL immagine valido con `https://` o `http://`.")
                        nome_salv = scarica_immagine_web(fonte_txt, r_titolo)
                    else:
                        st.error("Inserisci un link immagine oppure carica un file.")

                    if nome_salv:
                        risorse["immagini"].append({
                            "titolo": r_titolo.strip() or nome_salv,
                            "file": nome_salv,
                            "fonte_url": fonte_txt,
                        })
                        salva_risorse(risorse)
                        st.success(f"Immagine '{nome_salv}' aggiunta!")
                        st.rerun()
                except Exception as exc:
                    st.error(f"Impossibile salvare l'immagine: {exc}")

        if risorse.get("link") or risorse.get("immagini"):
            st.divider()
            st.markdown("**Rimuovi elementi esistenti**")
            if risorse.get("link"):
                for idx_l, item_l in enumerate(list(risorse["link"])):
                    c_txt, c_del = st.columns([4, 1])
                    c_txt.write(f"🔗 **{item_l.get('titolo', '')}** — `{item_l.get('url', '')}`")
                    if c_del.button("Elimina", key=f"del_link_{idx_l}"):
                        risorse["link"].pop(idx_l)
                        salva_risorse(risorse)
                        st.rerun()

            if risorse.get("immagini"):
                for idx_i, item_i in enumerate(list(risorse["immagini"])):
                    c_txt, c_del = st.columns([4, 1])
                    c_txt.write(f"🖼️ **{item_i.get('titolo', '')}** (`{item_i.get('file', '')}`)")
                    if c_del.button("Elimina", key=f"del_rimg_{idx_i}"):
                        risorse["immagini"].pop(idx_i)
                        salva_risorse(risorse)
                        st.rerun()

    # --- OPZIONE 7: PERSONALIZZA TITOLI, ETICHETTE & STILI ---
    elif azione == "🏷️ Personalizza Titoli & Etichette":
        st.subheader("Personalizza Titoli, Etichette & Caratteri")
        nomi_font = list(FONT_OPZIONI.keys())
        nomi_stili = list(STILE_TESTO_OPZIONI.keys())

        with st.form("form_etichette_home"):
            st.markdown("**1. Testi della Home**")
            c_h1, c_h2 = st.columns(2)
            with c_h1:
                e_titolo = st.text_input("Titolo principale", value=etichette["titolo_home"])
                e_mappa = st.text_input("Etichetta Mappa Generale", value=etichette["expander_mappa"])
                e_ricerca = st.text_input("Etichetta barra di ricerca", value=etichette["etichetta_ricerca"])
            with c_h2:
                e_sottotitolo = st.text_input("Sottotitolo", value=etichette["sottotitolo_home"])
                e_risorse = st.text_input("Etichetta Link & Immagini Manifestazione", value=etichette["expander_risorse"])
                e_postazioni = st.text_input("Intestazione elenco postazioni", value=etichette["titolo_postazioni"])

            st.markdown("**2. Etichette dei campi delle postazioni**")
            c_f1, c_f2 = st.columns(2)
            with c_f1:
                e_campo_id = st.text_input("Etichetta 1° campo (es. Codice Postazione)", value=etichette["campo_id"])
                e_campo_nome = st.text_input("Etichetta 2° campo (es. Nome Incrocio)", value=etichette["campo_nome"])
                e_campo_radio = st.text_input("Etichetta 3° campo (es. Codice radio)", value=etichette["campo_radio"])
            with c_f2:
                e_campo_pers = st.text_input("Etichetta 4° campo (es. Personale assegnato)", value=etichette["campo_personale"])
                e_campo_comm = st.text_input("Etichetta 5° campo (es. Commenti)", value=etichette["campo_commenti"])

            st.divider()
            st.markdown("**3. Carattere, Grandezza, Stile e Colore (salvati automaticamente)**")

            st.caption("Titolo principale")
            st1, st2, st3, st4 = st.columns([2, 1, 1.3, 1])
            with st1:
                f_tit = st.selectbox("Font titolo", nomi_font, index=nomi_font.index(etichette["stile_titolo_font"]) if etichette["stile_titolo_font"] in nomi_font else 0)
            with st2:
                s_tit = st.number_input("Grandezza (px)", min_value=16, max_value=60, value=int(etichette["stile_titolo_size"]), key="sz_tit")
            with st3:
                w_tit = st.selectbox("Stile", nomi_stili, index=nomi_stili.index(etichette["stile_titolo_peso"]) if etichette["stile_titolo_peso"] in nomi_stili else 1, key="wt_tit")
            with st4:
                c_tit = st.color_picker("Colore", value=etichette["stile_titolo_colore"], key="cl_tit")

            st.caption("Sottotitolo della Home")
            ss1, ss2, ss3, ss4 = st.columns([2, 1, 1.3, 1])
            with ss1:
                f_sot = st.selectbox("Font sottotitolo", nomi_font, index=nomi_font.index(etichette["stile_sottotitolo_font"]) if etichette["stile_sottotitolo_font"] in nomi_font else 0)
            with ss2:
                s_sot = st.number_input("Grandezza (px)", min_value=12, max_value=42, value=int(etichette["stile_sottotitolo_size"]), key="sz_sot")
            with ss3:
                w_sot = st.selectbox("Stile", nomi_stili, index=nomi_stili.index(etichette["stile_sottotitolo_peso"]) if etichette["stile_sottotitolo_peso"] in nomi_stili else 0, key="wt_sot")
            with ss4:
                c_sot = st.color_picker("Colore", value=etichette["stile_sottotitolo_colore"], key="cl_sot")

            st.caption("Intestazioni ed Etichette (es. Codice radio, Personale assegnato, Commenti...)")
            se1, se2, se3, se4 = st.columns([2, 1, 1.3, 1])
            with se1:
                f_eti = st.selectbox("Font etichette", nomi_font, index=nomi_font.index(etichette["stile_etichette_font"]) if etichette["stile_etichette_font"] in nomi_font else 0)
            with se2:
                s_eti = st.number_input("Grandezza (px)", min_value=12, max_value=36, value=int(etichette["stile_etichette_size"]), key="sz_eti")
            with se3:
                w_eti = st.selectbox("Stile", nomi_stili, index=nomi_stili.index(etichette["stile_etichette_peso"]) if etichette["stile_etichette_peso"] in nomi_stili else 1, key="wt_eti")
            with se4:
                c_eti = st.color_picker("Colore", value=etichette["stile_etichette_colore"], key="cl_eti")

            st.caption("Testo interno alle etichette (nomi personale, commenti, valori postazione)")
            sc1, sc2, sc3, sc4 = st.columns([2, 1, 1.3, 1])
            with sc1:
                f_con = st.selectbox("Font testi interni", nomi_font, index=nomi_font.index(etichette["stile_contenuti_font"]) if etichette["stile_contenuti_font"] in nomi_font else 0)
            with sc2:
                s_con = st.number_input("Grandezza (px)", min_value=12, max_value=36, value=int(etichette["stile_contenuti_size"]), key="sz_con")
            with sc3:
                w_con = st.selectbox("Stile", nomi_stili, index=nomi_stili.index(etichette["stile_contenuti_peso"]) if etichette["stile_contenuti_peso"] in nomi_stili else 0, key="wt_con")
            with sc4:
                c_con = st.color_picker("Colore", value=etichette["stile_contenuti_colore"], key="cl_con")

            salva_et = st.form_submit_button("Pubblica testi e stili", type="primary", use_container_width=True)
            if salva_et:
                nuove_et = {
                    "titolo_home": e_titolo.strip() or ETICHETTE_DEFAULT["titolo_home"],
                    "sottotitolo_home": e_sottotitolo.strip() or ETICHETTE_DEFAULT["sottotitolo_home"],
                    "expander_mappa": e_mappa.strip() or ETICHETTE_DEFAULT["expander_mappa"],
                    "expander_risorse": e_risorse.strip() or ETICHETTE_DEFAULT["expander_risorse"],
                    "etichetta_ricerca": e_ricerca.strip() or ETICHETTE_DEFAULT["etichetta_ricerca"],
                    "titolo_postazioni": e_postazioni.strip() or ETICHETTE_DEFAULT["titolo_postazioni"],
                    "campo_id": e_campo_id.strip() or ETICHETTE_DEFAULT["campo_id"],
                    "campo_nome": e_campo_nome.strip() or ETICHETTE_DEFAULT["campo_nome"],
                    "campo_radio": e_campo_radio.strip() or ETICHETTE_DEFAULT["campo_radio"],
                    "campo_personale": e_campo_pers.strip() or ETICHETTE_DEFAULT["campo_personale"],
                    "campo_commenti": e_campo_comm.strip() or ETICHETTE_DEFAULT["campo_commenti"],
                    "stile_titolo_font": f_tit,
                    "stile_titolo_size": int(s_tit),
                    "stile_titolo_colore": c_tit,
                    "stile_titolo_peso": w_tit,
                    "stile_sottotitolo_font": f_sot,
                    "stile_sottotitolo_size": int(s_sot),
                    "stile_sottotitolo_colore": c_sot,
                    "stile_sottotitolo_peso": w_sot,
                    "stile_etichette_font": f_eti,
                    "stile_etichette_size": int(s_eti),
                    "stile_etichette_colore": c_eti,
                    "stile_etichette_peso": w_eti,
                    "stile_contenuti_font": f_con,
                    "stile_contenuti_size": int(s_con),
                    "stile_contenuti_colore": c_con,
                    "stile_contenuti_peso": w_con,
                }
                salva_etichette(nuove_et)
                st.success("Testi, caratteri e colori salvati!")
                st.rerun()

        if st.button("Ripristina etichette e stili predefiniti"):
            salva_etichette(dict(ETICHETTE_DEFAULT))
            st.success("Etichette e stili ripristinati ai valori predefiniti.")
            st.rerun()