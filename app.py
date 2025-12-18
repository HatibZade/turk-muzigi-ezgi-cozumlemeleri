import streamlit as st
import yaml
from pathlib import Path

st.set_page_config(page_title="Türk Müziği Ezgi Çözümlemeleri", layout="wide")
st.title("🎼 Türk Müziği Ezgi Çözümlemeleri")
st.caption("Emrah Hatipoğlu")

DATA_PATH = Path("data") / "makamlar.yaml"

if not DATA_PATH.exists():
    st.error(f"Veri dosyası bulunamadı: {DATA_PATH}. Lütfen data/makamlar.yaml dosyasını kontrol edin.")
    st.stop()

with open(DATA_PATH, "r", encoding="utf-8") as f:
    makamlar = yaml.safe_load(f)

if not isinstance(makamlar, list):
    st.error("makamlar.yaml formatı hatalı: en üst seviye bir liste ([- ...]) olmalı.")
    st.stop()

names = [m.get("name","(isimsiz)") for m in makamlar]
secili = st.selectbox("Ezgi için olası makam profili", names)

makam = next((m for m in makamlar if m.get("name")==secili), None)
if makam is None:
    st.error("Seçilen profil bulunamadı.")
    st.stop()

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Tanım (Profil)")
    st.json(makam, expanded=True)

with col2:
    st.subheader("Ezgiye Göre Özet")
    ns = makam.get("nazari_seyir", {})
    st.markdown(
        f"**Nazari Seyir**: Âgâz **{', '.join(ns.get('agaz', []))}**, "
        f"Merkez **{', '.join(ns.get('kutb', []))}**, "
        f"Karar **{', '.join(ns.get('karar', []))}**"
    )
    asa = makam.get("asil_seyir_alani", {})
    st.markdown(f"**Asıl Seyir Alanı**: **{asa.get('alt','?')} – {asa.get('ust','?')}**")
    kp = makam.get("kullanilan_perdeler", {})
    nim = kp.get("nim", [])
    if isinstance(nim, str):
        nim = [nim]
    st.markdown("**Nim Perdeler**: " + (", ".join(nim) if nim else "—"))
    sus = makam.get("susleyen_perdeler", [])
    st.markdown("**Süsleyen Perdeler**: " + (", ".join(sus) if sus else "—"))
    ts = makam.get("lahni_seyir", {}).get("tasarruflar", [])
    if ts:
        st.markdown("**Lahnî Seyir Gözlemleri**")
        for t in ts:
            st.markdown(f"- {t}")

st.divider()
st.caption("Bu uygulama ezgiden hareketle çözümleme yapmayı hedefler; makam adları çıkarımsaldır.")
