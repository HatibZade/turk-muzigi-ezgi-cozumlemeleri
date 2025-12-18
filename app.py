import streamlit as st
import yaml
from pathlib import Path
import base64
import xml.etree.ElementTree as ET
from collections import Counter

# ------------------ AYARLAR ------------------
st.set_page_config(page_title="Türk Müziği Ezgi Çözümlemeleri", layout="wide")
st.title("🎼 Türk Müziği Ezgi Çözümlemeleri")
st.caption("Emrah Hatipoğlu")

DATA_PATH = Path("data") / "makamlar.yaml"

# ------------------ YARDIMCI FONKSİYONLAR ------------------
def show_pdf(file_bytes: bytes):
    b64 = base64.b64encode(file_bytes).decode("utf-8")
    html = f"""
    <iframe src="data:application/pdf;base64,{b64}"
            width="100%" height="750" style="border:none;"></iframe>
    """
    st.markdown(html, unsafe_allow_html=True)

def show_image(file_bytes: bytes):
    st.image(file_bytes, use_container_width=True)

def extract_features_from_musicxml(file_bytes: bytes):
    root = ET.fromstring(file_bytes)
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
            pitches.append((step, int(octave), int(float(alter))))

    if not pitches:
        return {}

    last_pitch = pitches[-1]
    center_pitch = Counter(pitches).most_common(1)[0][0]

    step_to_semi = {"C":0,"D":2,"E":4,"F":5,"G":7,"A":9,"B":11}
    def to_midi(p):
        s, o, a = p
        return (o + 1) * 12 + step_to_semi.get(s, 0) + a

    midis = [to_midi(p) for p in pitches]

    return {
        "karar": last_pitch,
        "merkez": center_pitch,
        "range": (min(midis), max(midis))
    }

def score_profiles(makamlar, karar=None, merkez=None, alt=None, ust=None, nim_list=None):
    nim_list = nim_list or []
    results = []

    for m in makamlar:
        score = 0
        reasons = []

        ns = m.get("nazari_seyir", {})
        asa = m.get("asil_seyir_alani", {})
        kp = m.get("kullanilan_perdeler", {})
        prof_nim = kp.get("nim", [])
        if isinstance(prof_nim, str):
            prof_nim = [prof_nim]

        if karar and karar in (ns.get("karar") or []):
            score += 3
            reasons.append(f"Karar uyuşuyor: {karar}")

        if merkez and merkez in (ns.get("kutb") or []):
            score += 2
            reasons.append(f"Merkez uyuşuyor: {merkez}")

        if alt and asa.get("alt") == alt:
            score += 1
            reasons.append(f"Alt sınır: {alt}")

        if ust and asa.get("ust") == ust:
            score += 1
            reasons.append(f"Üst sınır: {ust}")

        if nim_list:
            inter = set(nim_list).intersection(set(prof_nim))
            if inter:
                score += 2
                reasons.append(f"Nim kesişimi: {', '.join(inter)}")

        if score > 0:
            results.append((score, m.get("name"), reasons))

    results.sort(key=lambda x: x[0], reverse=True)
    return results[:5]

# ------------------ VERİYİ OKU ------------------
if not DATA_PATH.exists():
    st.error("data/makamlar.yaml bulunamadı.")
    st.stop()

with open(DATA_PATH, "r", encoding="utf-8") as f:
    makamlar = yaml.safe_load(f)

names = [m.get("name") for m in makamlar]

# ------------------ SEKME YAPISI ------------------
tab1, tab2 = st.tabs(["📘 Ezgi Profilleri", "🎼 Nota Yükle"])

# ------------------ TAB 1: PROFİLLER ------------------
with tab1:
    secili = st.selectbox("Ezgi için olası profil", names)
    makam = next(m for m in makamlar if m.get("name") == secili)

    col1, col2 = st.columns([1,1])

    with col1:
        st.subheader("Ezgi Profili")

        kp = makam.get("kullanilan_perdeler", {})
        st.markdown("### Kullanılan Perdeler")
        st.markdown(f"**Tam:** {kp.get('tam','—')}")
        nim = kp.get("nim", [])
        if isinstance(nim, str): nim = [nim]
        st.markdown("**Nim:** " + (", ".join(nim) if nim else "—"))

        ns = makam.get("nazari_seyir", {})
        st.markdown("### Nazari Seyir")
        st.markdown(f"- Âgâz: {', '.join(ns.get('agaz',[]))}")
        st.markdown(f"- Merkez: {', '.join(ns.get('kutb',[]))}")
        st.markdown(f"- Karar: {', '.join(ns.get('karar',[]))}")

        asa = makam.get("asil_seyir_alani", {})
        st.markdown("### Asıl Seyir Alanı")
        st.markdown(f"{asa.get('alt')} – {asa.get('ust')}")

        st.markdown("### Süsleyen Perdeler")
        st.markdown(", ".join(makam.get("susleyen_perdeler",[])))

        st.markdown("### Lahnî Seyir")
        for t in makam.get("lahni_seyir",{}).get("tasarruflar",[]):
            st.markdown(f"- {t}")

    with col2:
        st.subheader("Özet")
        st.info("Bu panel seçilen ezgi profilinin pedagojik özetidir.")


# ------------------ TAB 2: NOTA YÜKLE ------------------
with tab2:
    st.subheader("🎼 Nota Yükleme ve Ezgi Çözümleme")

    uploaded = st.file_uploader(
        "Nota dosyasını yükleyin",
        type=["pdf","png","jpg","jpeg","musicxml","xml"]
    )

    if uploaded:
        file_bytes = uploaded.getvalue()
        ext = uploaded.name.split(".")[-1].lower()

        st.success(f"Yüklenen dosya: {uploaded.name}")
        st.markdown("### Önizleme")

        if ext == "pdf":
            show_pdf(file_bytes)
        elif ext in ["png","jpg","jpeg"]:
            show_image(file_bytes)
        else:
            st.info("MusicXML yüklendi – otomatik çıkarım aktif.")

        auto = {}
        if ext in ["musicxml","xml"]:
            auto = extract_features_from_musicxml(file_bytes)
            if auto:
                st.info(f"Otomatik çıkarım (kaba): merkez={auto.get('merkez')}, karar={auto.get('karar')}")

        st.markdown("### Ezgi Özellikleri (manuel)")
        colA, colB = st.columns(2)

        with colA:
            karar = st.text_input("Karar perdesi")
            merkez = st.text_input("Merkez perdesi")
            alt = st.text_input("Alan alt sınırı")
            ust = st.text_input("Alan üst sınırı")

        with colB:
            nim_csv = st.text_input("Nim perdeler (virgülle)")
            nim_list = [x.strip() for x in nim_csv.split(",") if x.strip()]

        if st.button("Olası profilleri öner"):
            results = score_profiles(
                makamlar,
                karar=karar or None,
                merkez=merkez or None,
                alt=alt or None,
                ust=ust or None,
                nim_list=nim_list
            )

            if not results:
                st.warning("Eşleşme bulunamadı.")
            else:
                st.success("En olası profiller:")
                for sc, name, reasons in results:
                    st.markdown(f"**{name}** — skor {sc}")
                    for r in reasons:
                        st.markdown(f"- {r}")

st.divider()
st.caption("Bu uygulama ezgiden hareketle çözümleme yapar; sonuçlar çıkarımsaldır.")
