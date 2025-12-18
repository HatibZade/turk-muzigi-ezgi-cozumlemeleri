import streamlit as st
import yaml
from pathlib import Path
import unicodedata

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

# ------------------ PUANLAMA ------------------
def score_profiles(profiles, karar=None, merkez=None, alt=None, ust=None, nim_list=None):
    nim_list = nim_list or []

    karar_n = normalize_perde(karar) if karar else ""
    merkez_n = normalize_perde(merkez) if merkez else ""
    alt_n = normalize_perde(alt) if alt else ""
    ust_n = normalize_perde(ust) if ust else ""
    nim_n = [normalize_perde(x) for x in nim_list]

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

        if nim_n and prof_nim_n:
            inter = sorted(set(nim_n).intersection(set(prof_nim_n)))
            if inter:
                score += 2
                reasons.append("Nim kesişimi var")

        if score > 0:
            scored.append((score, m.get("name", "(isimsiz)"), reasons))

    scored.sort(key=lambda x: x[0], reverse=True)
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

# ------------------ UI LISTELER ------------------
TAM_PERDELER_UI = [
    "yegâh", "aşîrān", "ırâk", "rast", "dügâh", "segâh", "çargâh", "nevâ", "hüseynî",
    "evc", "gerdaniyye", "muhayyer", "tîz segâh", "tîz çargâh", "tîz nevâ"
]
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
ALL_PERDELER_UI = ["—"] + TAM_PERDELER_UI

# ------------------ SEKME ------------------
tab1, tab2 = st.tabs(["📘 Ezgi Profilleri", "🎼 Nota Yükle"])

# ------------------ TAB 1 ------------------
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
        st.markdown(f"- **Âgâz:** {', '.join((ns.get('agaz') or [])) if isinstance(ns.get('agaz'), list) else (ns.get('agaz') or '—')}")
        st.markdown(f"- **Merkez:** {', '.join((ns.get('kutb') or [])) if isinstance(ns.get('kutb'), list) else (ns.get('kutb') or '—')}")
        st.markdown(f"- **Karar:** {', '.join((ns.get('karar') or [])) if isinstance(ns.get('karar'), list) else (ns.get('karar') or '—')}")

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
        st.info("Seçilen profilin hızlı özeti. Nota yükleme ve olasılık için diğer sekmeyi kullan.")

        ns = prof.get("nazari_seyir", {}) or {}
        asa = prof.get("asil_seyir_alani", {}) or {}
        kp = prof.get("kullanilan_perdeler", {}) or {}

        st.markdown(
            f"**Normalize edilmiş (eşleşme için):** "
            f"Karar={', '.join(normalize_list(ns.get('karar'))) or '—'}, "
            f"Merkez={', '.join(normalize_list(ns.get('kutb'))) or '—'}, "
            f"Alan={normalize_perde(asa.get('alt','—'))}–{normalize_perde(asa.get('ust','—'))}"
        )
        st.caption("Not: Şapkalı/üst çizgili/düz yazımlar otomatik normalize edilir.")

# ------------------ TAB 2 ------------------
with tab2:
    st.subheader("🎼 Nota Yükleme ve Olası Profil Önerisi")

    st.warning(
        "PDF notadan otomatik perde/seyir çıkarımı (OMR) bu sürümde yok. "
        "PDF'yi yükleyip aşağıdan karar/merkez/alan/nim seçerek olasılık alırsınız."
    )

    uploaded = st.file_uploader("PDF nota yükle", type=["pdf"])
    if uploaded:
        st.success(f"PDF yüklendi: {uploaded.name}")
        # Google/iframe görüntüleme yok: sadece indirme
        st.download_button(
            "📥 Yüklenen PDF'yi indir",
            data=uploaded.getvalue(),
            file_name=uploaded.name,
            mime="application/pdf"
        )
        st.caption("Görüntüleme bazı ortamlarda engellenebildiği için önizleme kaldırıldı.")

    st.divider()
    st.markdown("### Ezgi Özelliklerini Seç (v1)")

    colA, colB = st.columns(2)
    with colA:
        karar_ui = st.selectbox("Karar perdesi", ALL_PERDELER_UI, index=0)
        merkez_ui = st.selectbox("Merkez perdesi", ALL_PERDELER_UI, index=0)
        alt_ui = st.selectbox("Asıl alan alt sınırı", ALL_PERDELER_UI, index=0)
        ust_ui = st.selectbox("Asıl alan üst sınırı", ALL_PERDELER_UI, index=0)

    with colB:
        nim_ui = st.multiselect("Nim perdeler", NIM_PERDELER_UI, default=[])

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
