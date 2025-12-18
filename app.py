import streamlit as st
import yaml
from pathlib import Path
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter

# ------------------ SAYFA AYARLARI ------------------
st.set_page_config(page_title="Türk Müziği Ezgi Çözümlemeleri", layout="wide")
st.title("🎼 Türk Müziği Ezgi Çözümlemeleri")
st.caption("Emrah Hatipoğlu")

DATA_PATH = Path("data") / "makamlar.yaml"

# ------------------ NORMALİZASYON ------------------
def normalize_perde(s: str) -> str:
    if not s:
        return ""
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    tr_map = {
        "ş": "s", "ğ": "g", "ı": "i", "ö": "o", "ü": "u", "ç": "c",
        "â": "a", "î": "i", "û": "u",
        "ā": "a", "ī": "i", "ū": "u",
    }
    for k, v in tr_map.items():
        s = s.replace(k, v)
    s = " ".join(s.split())
    return s

def normalize_list(values):
    if values is None:
        return []
    if isinstance(values, list):
        return [normalize_perde(v) for v in values if v is not None]
    return [normalize_perde(values)]

# ------------------ MUSICXML (BASİT) OKUMA ------------------
STEP_TO_SEMI = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

def pitch_to_midi(step: str, octave: int, alter: int = 0) -> int:
    return (octave + 1) * 12 + STEP_TO_SEMI.get(step, 0) + int(alter)

def parse_musicxml_bytes(file_bytes: bytes):
    try:
        root = ET.fromstring(file_bytes)
    except Exception:
        return []
    pitches = []
    for note in root.findall(".//note"):
        if note.find("rest") is not None:
            continue
        pitch = note.find("pitch")
        if pitch is None:
            continue
        step = pitch.findtext("step")
        octave = pitch.findtext("octave")
        alter = pitch.findtext("alter") or "0"
        if step and octave:
            try:
                pitches.append((step, int(octave), int(float(alter))))
            except Exception:
                pass
    return pitches

TAM_PERDELER_UI = [
    "yegâh", "aşîrān", "ırâk", "rast", "dügâh", "segâh", "çargâh", "nevâ", "hüseynî",
    "evc", "gerdaniyye", "muhayyer", "tîz segâh", "tîz çargâh", "tîz nevâ"
]
ALL_PERDELER_UI = ["—"] + TAM_PERDELER_UI

NIM_PERDELER_UI = [
    "nerm bayatî", "nerm hisar", "pest aşîrān",
    "acem-aşîrān", "dik acem-aşîrān",
    "geveşt",
    "şurî", "zengûle", "pest dügâh",
    "kürdî", "dik kürdî",
    "buselik", "nişābūr (buselik)",
    "sabâ", "hicâz", "pest nevâ",
    "bayatî", "hisar", "pest hüseynî",
    "acem", "dik acem",
    "mahûr",
    "tîz şurî", "şehnāz", "pest muhayyer",
    "sünbüle", "dik sünbüle"
]

def build_reference_midi_map(rast_midi: int = 60):
    ref = {
        "rast": rast_midi,
        "dügâh": rast_midi + 2,
        "segâh": rast_midi + 4,
        "çargâh": rast_midi + 5,
        "nevâ": rast_midi + 7,
        "hüseynî": rast_midi + 9,
        "evc": rast_midi + 11,
        "gerdaniyye": rast_midi + 12,
        "muhayyer": rast_midi + 14,
        "tîz segâh": rast_midi + 16,
        "tîz çargâh": rast_midi + 17,
        "tîz nevâ": rast_midi + 19,
        "ırâk": rast_midi - 1,
        "aşîrān": rast_midi - 3,
        "yegâh": rast_midi - 5,
    }
    return {normalize_perde(k): v for k, v in ref.items()}

def nearest_tam_perde_from_midi(midi_val: int, midi_map_norm: dict):
    best = None
    best_diff = 999
    for perde_norm, p_midi in midi_map_norm.items():
        diff = abs(midi_val - p_midi)
        if diff < best_diff:
            best, best_diff = perde_norm, diff
    if best is None or best_diff > 2:
        return None
    return best

def norm_to_ui_perde(perde_norm: str):
    if not perde_norm:
        return None
    for ui in TAM_PERDELER_UI:
        if normalize_perde(ui) == perde_norm:
            return ui
    return None

def auto_features_from_musicxml(file_bytes: bytes, rast_midi: int):
    pitches = parse_musicxml_bytes(file_bytes)
    if not pitches:
        return None

    midis = [pitch_to_midi(s, o, a) for (s, o, a) in pitches]
    last_midi = midis[-1]
    center_midi = Counter(midis).most_common(1)[0][0]
    lo, hi = min(midis), max(midis)

    midi_map_norm = build_reference_midi_map(rast_midi)

    karar_norm = nearest_tam_perde_from_midi(last_midi, midi_map_norm)
    merkez_norm = nearest_tam_perde_from_midi(center_midi, midi_map_norm)
    alt_norm = nearest_tam_perde_from_midi(lo, midi_map_norm)
    ust_norm = nearest_tam_perde_from_midi(hi, midi_map_norm)

    return {
        "karar_ui": norm_to_ui_perde(karar_norm),
        "merkez_ui": norm_to_ui_perde(merkez_norm),
        "alt_ui": norm_to_ui_perde(alt_norm),
        "ust_ui": norm_to_ui_perde(ust_norm),
        "debug": {"last_midi": last_midi, "center_midi": center_midi, "range_midi": (lo, hi)}
    }

# ------------------ PUANLAMA (GÜNCELLENMİŞ) ------------------
def score_profiles(profiles, karar=None, merkez=None, alt=None, ust=None, nim_list=None):
    """
    Güncellenmiş mantık:
    - Karar eşleşmesi: +3
    - Merkez eşleşmesi: +2
    - Alan alt: +1
    - Alan üst: +1
    - Nim kesişimi: +2
    - ÖNEMLİ: Kullanıcı nim GİRMEDİYSE:
        * Profilin nim'i VARSA: -2 (Hicaz gibi profillerin sebepsiz öne çıkmasını azaltır)
        * Profilin nim'i YOKSA: +1 (Nevâ gibi profillerin öne gelmesini sağlar)
    """
    nim_list = nim_list or []

    karar_n = normalize_perde(karar) if karar else ""
    merkez_n = normalize_perde(merkez) if merkez else ""
    alt_n = normalize_perde(alt) if alt else ""
    ust_n = normalize_perde(ust) if ust else ""
    nim_n = [normalize_perde(x) for x in nim_list]

    user_provided_nim = len(nim_n) > 0

    scored = []

    for m in profiles:
        score = 0
        reasons = []

        ns = m.get("nazari_seyir", {}) or {}
        asa = m.get("asil_seyir_alani", {}) or {}
        kp = m.get("kullanilan_perdeler", {}) or {}

        prof_karar_n = normalize_list(ns.get("karar"))
        prof_kutb_n = normalize_list(ns.get("kutb"))
        prof_alt_n = normalize_perde(asa.get("alt", ""))
        prof_ust_n = normalize_perde(asa.get("ust", ""))
        prof_nim_n = normalize_list(kp.get("nim"))
        prof_has_nim = len(prof_nim_n) > 0

        if karar_n and karar_n in prof_karar_n:
            score += 3
            reasons.append(f"Karar eşleşti: {karar}")

        if merkez_n and merkez_n in prof_kutb_n:
            score += 2
            reasons.append(f"Merkez eşleşti: {merkez}")

        if alt_n and prof_alt_n and alt_n == prof_alt_n:
            score += 1
            reasons.append(f"Asıl alan alt sınır eşleşti: {alt}")

        if ust_n and prof_ust_n and ust_n == prof_ust_n:
            score += 1
            reasons.append(f"Asıl alan üst sınır eşleşti: {ust}")

        if user_provided_nim and prof_has_nim:
            inter = sorted(set(nim_n).intersection(set(prof_nim_n)))
            if inter:
                score += 2
                reasons.append("Nim kesişimi var")

        # Yeni ayırt edici kural
        if not user_provided_nim:
            if prof_has_nim:
                score -= 2
                reasons.append("Nim verilmedi: nimli profiller geriye düşürüldü")
            else:
                score += 1
                reasons.append("Nim verilmedi: nimsiz profiller öne alındı")

        # Skor 0 altına düşerse listelemeyelim (gürültü azaltır)
        if score > 0:
            scored.append((score, m.get("name", "(isimsiz)"), reasons))

    # Tie-break: skor eşitse, daha az “ceza” içeren (daha kısa gerekçe) öne gelsin
    scored.sort(key=lambda x: (x[0], -len(x[2])), reverse=True)
    return scored[:7]

# ------------------ VERİ ------------------
if not DATA_PATH.exists():
    st.error("Veri dosyası bulunamadı: data/makamlar.yaml")
    st.stop()

with open(DATA_PATH, "r", encoding="utf-8") as f:
    profiles = yaml.safe_load(f)

if not isinstance(profiles, list) or not profiles:
    st.error("data/makamlar.yaml boş veya format hatalı. En üst seviye bir liste olmalı.")
    st.stop()

names = [m.get("name", "(isimsiz)") for m in profiles]

# ------------------ SESSION STATE ------------------
for key in ["karar_ui", "merkez_ui", "alt_ui", "ust_ui"]:
    if key not in st.session_state:
        st.session_state[key] = "—"
if "nim_ui" not in st.session_state:
    st.session_state.nim_ui = []

# ------------------ SEKME ------------------
tab1, tab2 = st.tabs(["📘 Ezgi Profilleri", "🎼 Nota Yükle"])

with tab1:
    secili = st.selectbox("Ezgi için olası profil", names)
    prof = next((m for m in profiles if m.get("name") == secili), None)
    if prof is None:
        st.error("Seçilen profil bulunamadı.")
        st.stop()

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Ezgi Profili")

        kp = prof.get("kullanilan_perdeler", {}) or {}
        ns = prof.get("nazari_seyir", {}) or {}
        asa = prof.get("asil_seyir_alani", {}) or {}

        st.markdown("### Kullanılan Perdeler")
        st.markdown(f"**Tam:** {kp.get('tam', '—')}")
        nim = kp.get("nim", [])
        if not isinstance(nim, list):
            nim = [nim] if nim else []
        st.markdown("**Nim:** " + (", ".join(nim) if nim else "—"))

        st.markdown("### Nazari Seyir")
        agaz = ns.get("agaz", [])
        kutb = ns.get("kutb", [])
        karar = ns.get("karar", [])
        if not isinstance(agaz, list): agaz = [agaz] if agaz else []
        if not isinstance(kutb, list): kutb = [kutb] if kutb else []
        if not isinstance(karar, list): karar = [karar] if karar else []
        st.markdown(f"- **Âgâz:** {', '.join(agaz) or '—'}")
        st.markdown(f"- **Merkez:** {', '.join(kutb) or '—'}")
        st.markdown(f"- **Karar:** {', '.join(karar) or '—'}")

        st.markdown("### Asıl Seyir Alanı")
        st.markdown(f"**{asa.get('alt','—')} – {asa.get('ust','—')}**")

        st.markdown("### Süsleyen Perdeler")
        sus = prof.get("susleyen_perdeler", [])
        if not isinstance(sus, list):
            sus = [sus] if sus else []
        st.markdown(", ".join(sus) if sus else "—")

        st.markdown("### Lahnî Seyir Gözlemleri")
        ts = (prof.get("lahni_seyir") or {}).get("tasarruflar", [])
        if not isinstance(ts, list):
            ts = [ts] if ts else []
        if ts:
            for t in ts:
                st.markdown(f"- {t}")
        else:
            st.markdown("—")

    with col2:
        st.subheader("Kısa Özet")
        st.info("Nota yükleyip olasılık üretmek için diğer sekmeyi kullan.")

with tab2:
    st.subheader("🎼 Nota Yükle → Ezgi Özellikleri → Olası Profil")

    uploaded = st.file_uploader(
        "Nota dosyası yükle (PDF / MusicXML / XML)",
        type=["pdf", "musicxml", "xml"]
    )

    with st.expander("MusicXML eşleme ayarı (isteğe bağlı)", expanded=False):
        rast_ref = st.selectbox(
            "Rast hangi batı notasına denk varsayılsın?",
            ["C4 (varsayılan)", "D4", "E4", "F4", "G4", "A4", "B4"],
            index=0
        )
        rast_midi_map = {"C4 (varsayılan)": 60, "D4": 62, "E4": 64, "F4": 65, "G4": 67, "A4": 69, "B4": 71}
        rast_midi = rast_midi_map[rast_ref]

    if uploaded:
        file_bytes = uploaded.getvalue()
        ext = uploaded.name.split(".")[-1].lower()

        st.success(f"Yüklendi: {uploaded.name}")

        if ext == "pdf":
            st.download_button(
                "📥 PDF'yi indir",
                data=file_bytes,
                file_name=uploaded.name,
                mime="application/pdf"
            )
            st.info("PDF’den otomatik nota okuma (OMR) bu sürümde yok. Aşağıdan seçim yaparak olasılık alabilirsiniz.")

        if ext in ["musicxml", "xml"]:
            auto = auto_features_from_musicxml(file_bytes, rast_midi=rast_midi)
            if auto is None:
                st.warning("MusicXML okundu ama nota bulunamadı. Dosyayı kontrol edin.")
            else:
                st.success("MusicXML’den otomatik öneri çıkarıldı (v1).")
                st.write(f"- Karar: **{auto.get('karar_ui') or '—'}**")
                st.write(f"- Merkez: **{auto.get('merkez_ui') or '—'}**")
                st.write(f"- Alan: **{auto.get('alt_ui') or '—'} – {auto.get('ust_ui') or '—'}**")

                if st.button("⬇️ Bu önerileri seçimlere doldur"):
                    st.session_state.karar_ui = auto.get("karar_ui") or "—"
                    st.session_state.merkez_ui = auto.get("merkez_ui") or "—"
                    st.session_state.alt_ui = auto.get("alt_ui") or "—"
                    st.session_state.ust_ui = auto.get("ust_ui") or "—"
                    st.success("Seçimler güncellendi. Şimdi 'Olası profilleri öner' diyebilirsin.")

    st.divider()
    st.markdown("### Ezgi Özelliklerini Seç")

    colA, colB = st.columns(2)
    with colA:
        karar_ui = st.selectbox("Karar perdesi", ALL_PERDELER_UI, key="karar_ui")
        merkez_ui = st.selectbox("Merkez perdesi", ALL_PERDELER_UI, key="merkez_ui")
        alt_ui = st.selectbox("Asıl alan alt sınırı", ALL_PERDELER_UI, key="alt_ui")
        ust_ui = st.selectbox("Asıl alan üst sınırı", ALL_PERDELER_UI, key="ust_ui")

    with colB:
        nim_ui = st.multiselect("Nim perdeler", NIM_PERDELER_UI, default=st.session_state.nim_ui, key="nim_ui")
        st.caption("Nim seçmezsen, nimli profiller (örn. Hicaz) otomatik olarak biraz geriye düşer.")

    if st.button("Olası profilleri öner"):
        results = score_profiles(
            profiles,
            karar=None if karar_ui == "—" else karar_ui,
            merkez=None if merkez_ui == "—" else merkez_ui,
            alt=None if alt_ui == "—" else alt_ui,
            ust=None if ust_ui == "—" else ust_ui,
            nim_list=nim_ui
        )

        if not results:
            st.warning("Eşleşme bulunamadı. Özellikle karar ve merkez seçmeyi deneyin.")
        else:
            st.success("En olası profiller:")
            for sc, name, reasons in results:
                st.markdown(f"**{name}** — skor: **{sc}**")
                for r in reasons:
                    st.markdown(f"- {r}")

st.divider()
st.caption("Bu uygulama ezgiden hareketle çözümleme yapmayı hedefler; sonuçlar çıkarımsaldır.")
