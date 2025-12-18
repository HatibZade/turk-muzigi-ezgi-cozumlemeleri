import streamlit as st
import yaml
from pathlib import Path
import base64

# ------------------ SAYFA AYARLARI ------------------
st.set_page_config(page_title="Türk Müziği Ezgi Çözümlemeleri", layout="wide")
st.title("🎼 Türk Müziği Ezgi Çözümlemeleri")
st.caption("Emrah Hatipoğlu")

DATA_PATH = Path("data") / "makamlar.yaml"

# ------------------ YARDIMCILAR ------------------
def show_pdf(file_bytes: bytes):
    b64 = base64.b64encode(file_bytes).decode("utf-8")
    html = f"""
    <iframe src="data:application/pdf;base64,{b64}"
            width="100%" height="750" style="border:none;"></iframe>
    """
    st.markdown(html, unsafe_allow_html=True)

def show_image(file_bytes: bytes):
    st.image(file_bytes, use_container_width=True)

def as_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]

def score_profiles(profiles, karar=None, merkez=None, alt=None, ust=None, nim_list=None):
    """
    Basit puanlama:
    - Karar eşleşmesi: +3
    - Merkez (kutb) eşleşmesi: +2
    - Alan alt eşleşmesi: +1
    - Alan üst eşleşmesi: +1
    - Nim perdeler kesişimi: +2 (en az 1 ortak varsa)
    """
    nim_list = nim_list or []
    scored = []

    for m in profiles:
        score = 0
        reasons = []

        ns = m.get("nazari_seyir", {}) or {}
        asa = m.get("asil_seyir_alani", {}) or {}
        kp = m.get("kullanilan_perdeler", {}) or {}

        prof_karar = as_list(ns.get("karar"))
        prof_kutb = as_list(ns.get("kutb"))
        prof_nim = as_list(kp.get("nim"))

        if karar and karar in prof_karar:
            score += 3
            reasons.append(f"Karar eşleşti: {karar}")

        if merkez and merkez in prof_kutb:
            score += 2
            reasons.append(f"Merkez eşleşti: {merkez}")

        if alt and asa.get("alt") == alt:
            score += 1
            reasons.append(f"Asıl alan alt sınır eşleşti: {alt}")

        if ust and asa.get("ust") == ust:
            score += 1
            reasons.append(f"Asıl alan üst sınır eşleşti: {ust}")

        if nim_list:
            inter = sorted(set(nim_list).intersection(set(prof_nim)))
            if inter:
                score += 2
                reasons.append("Nim kesişimi: " + ", ".join(inter))

        if score > 0:
            scored.append((score, m.get("name", "(isimsiz)"), reasons))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:7]

# ------------------ VERİYİ OKU ------------------
if not DATA_PATH.exists():
    st.error("Veri dosyası bulunamadı: data/makamlar.yaml")
    st.stop()

with open(DATA_PATH, "r", encoding="utf-8") as f:
    profiles = yaml.safe_load(f)

if not isinstance(profiles, list) or not profiles:
    st.error("data/makamlar.yaml boş veya format hatalı. En üst seviye bir liste olmalı.")
    st.stop()

names = [m.get("name", "(isimsiz)") for m in profiles]

# ------------------ PERDE LİSTELERİ (SEÇMELİ GİRİŞ) ------------------
TAM_PERDELER = [
    "yegâh", "aşîrān", "ırâk", "rast", "dügâh", "segâh", "çargâh", "nevâ", "hüseynî",
    "evc", "gerdaniyye", "muhayyer", "tîz segâh", "tîz çargâh", "tîz nevâ"
]

NIM_PERDELER = [
    "nerm bayatî", "nerm hisar", "pest aşîrān",
    "acem-aşîrān", "dik acem-aşîrān",
    "geveşt",
    "şurî", "zengûle", "pest dügâh",
    "kürdî", "dik kürdî",
    "buselik", "nişābūr (buselik)",
    "sabâ", "hicaz", "pest nevâ",
    "bayatî", "hisar", "pest hüseynî",
    "acem", "dik acem",
    "mahûr",
    "tîz şurî", "şehnāz", "pest muhayyer",
    "sünbüle", "dik sünbüle"
]

ALL_PERDELER = ["—"] + TAM_PERDELER

# ------------------ SEKME YAPISI ------------------
tab1, tab2 = st.tabs(["📘 Ezgi Profilleri", "🎼 Nota Yükle"])

# ------------------ TAB 1: PROFİLLER ------------------
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
        nim = as_list(kp.get("nim"))
        st.markdown("**Nim:** " + (", ".join(nim) if nim else "—"))

        st.markdown("### Nazari Seyir")
        st.markdown(f"- **Âgâz:** {', '.join(as_list(ns.get('agaz'))) or '—'}")
        st.markdown(f"- **Merkez:** {', '.join(as_list(ns.get('kutb'))) or '—'}")
        st.markdown(f"- **Karar:** {', '.join(as_list(ns.get('karar'))) or '—'}")

        st.markdown("### Asıl Seyir Alanı")
        st.markdown(f"**{asa.get('alt','—')} – {asa.get('ust','—')}**")

        st.markdown("### Süsleyen Perdeler")
        sus = as_list(prof.get("susleyen_perdeler"))
        st.markdown(", ".join(sus) if sus else "—")

        st.markdown("### Lahnî Seyir Gözlemleri")
        ts = as_list((prof.get("lahni_seyir") or {}).get("tasarruflar"))
        if ts:
            for t in ts:
                st.markdown(f"- {t}")
        else:
            st.markdown("—")

    with col2:
        st.subheader("Kısa Özet")
        st.info("Bu panel, seçilen profilin hızlı özetidir. Nota analizinde, alttaki sekme kullanılır.")

        ns = prof.get("nazari_seyir", {}) or {}
        asa = prof.get("asil_seyir_alani", {}) or {}
        kp = prof.get("kullanilan_perdeler", {}) or {}

        st.markdown(
            f"**Nazari Seyir:** Âgâz **{', '.join(as_list(ns.get('agaz'))) or '—'}**, "
            f"Merkez **{', '.join(as_list(ns.get('kutb'))) or '—'}**, "
            f"Karar **{', '.join(as_list(ns.get('karar'))) or '—'}**"
        )
        st.markdown(f"**Asıl Seyir Alanı:** **{asa.get('alt','—')} – {asa.get('ust','—')}**")
        nim = as_list(kp.get("nim"))
        st.markdown("**Nim Perdeler:** " + (", ".join(nim) if nim else "—"))

# ------------------ TAB 2: NOTA YÜKLE ------------------
with tab2:
    st.subheader("🎼 Nota Yükleme ve Olası Profil Önerisi")

    st.caption(
        "Not: PDF/PNG/JPG yüklediğinizde sistem notayı otomatik okumaz (OMR henüz yok). "
        "Bu yüzden aşağıdan karar/merkez/alan/nim perdeleri seçerek öneri alırsınız."
    )

    uploaded = st.file_uploader(
        "Nota dosyasını yükleyin (PDF/PNG/JPG)",
        type=["pdf", "png", "jpg", "jpeg"]
    )

    if uploaded:
        file_bytes = uploaded.getvalue()
        ext = uploaded.name.split(".")[-1].lower()

        st.success(f"Yüklenen dosya: {uploaded.name}")
        st.markdown("### Önizleme")
        if ext == "pdf":
            show_pdf(file_bytes)
        else:
            show_image(file_bytes)

    st.divider()
    st.markdown("### Ezgi Özelliklerini Seç (v1)")

    colA, colB = st.columns(2)

    with colA:
        karar = st.selectbox("Karar perdesi", ALL_PERDELER, index=0)
        merkez = st.selectbox("Merkez perdesi", ALL_PERDELER, index=0)
        alt = st.selectbox("Asıl alan alt sınırı", ALL_PERDELER, index=0)
        ust = st.selectbox("Asıl alan üst sınırı", ALL_PERDELER, index=0)

    with colB:
        nim_list = st.multiselect("Nim perdeler", NIM_PERDELER, default=[])

    if st.button("Olası profilleri öner"):
        results = score_profiles(
            profiles,
            karar=None if karar == "—" else karar,
            merkez=None if merkez == "—" else merkez,
            alt=None if alt == "—" else alt,
            ust=None if ust == "—" else ust,
            nim_list=nim_list
        )

        if not results:
            st.warning("Eşleşme bulunamadı. Birkaç alan daha seçmeyi deneyin (özellikle karar/merkez).")
        else:
            st.success("En olası profiller:")
            for sc, name, reasons in results:
                st.markdown(f"**{name}** — skor: **{sc}**")
                for r in reasons:
                    st.markdown(f"- {r}")

st.divider()
st.caption("Bu uygulama ezgiden hareketle çözümleme yapmayı hedefler; sonuçlar çıkarımsaldır.")
