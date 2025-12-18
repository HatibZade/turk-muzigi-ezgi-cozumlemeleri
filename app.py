# app_latest.py
# Streamlit app: Makam olasılığı (Nazari Seyir: Âgâz, Kutb/Merkez, Karar)
# + Nim filtreleme (Nim perde adı delili ile)
# + MusicXML mikrotonal işaret teşhisi (sağ panel) — filtreyi DELMEZ.
#
# Gereksinimler:
#   pip install streamlit music21
#
# Not:
# - Makam önerisi için asıl kural: Kullanıcı Âgâz/Kutb/Karar veriyorsa, bu üçlü ile
#   çelişen makamlar ELENİR (tutarlılık filtresi). Skor sadece kalanlar arasında sıralama içindir.
# - Nim filtresi: Kullanıcı "nim perde adı delili" seçmezse, nim gerektiren makamlar (örn. Hicaz)
#   aday havuzundan çıkarılır. MusicXML’de mikro işaret tespiti sadece teşhistir.
#
# Mikrotonal işaret okuma (teşhis) — Halk müziği sayı yazımı dahil:
# - ♯ üzerinde sayı yoksa -> Bakıyye
# - ♯ üzerinde 5 varsa    -> Küçük Mücenneb
# - ♭ üzerinde sayı yoksa -> Küçük Mücenneb
# - ♭ üzerinde 4 varsa    -> Bakıyye
# - ♭ üzerinde 1/2/3      -> Koma/İrha
# - Oklu/özel işaretler (metinde pest/dik geçerse, sayı yoksa):
#     pest diyez -> Bakıyye
#     diyez      -> (yukarıdaki kural: sayı yoksa Bakıyye)
#     dik diyez  -> Büyük Mücenneb
#     dik bemol  -> Bakıyye
#     pest bemol -> Büyük Mücenneb
#     pest bekar <-> dik diyez  (Büyük Mücenneb)
#     dik bekar  <-> pest bemol (Büyük Mücenneb)

import io
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

try:
    from music21 import converter
    from music21 import note as m21note
    from music21 import chord as m21chord
    M21_OK = True
except Exception:
    M21_OK = False


# -----------------------------
# Yardımcılar
# -----------------------------
def norm(s: str) -> str:
    """
    Eşleştirme için normalizasyon.
    - Şapka/üst çizgi gibi telaffuz işaretlerini normalize eder (eşleştirme için),
      AMA UI etiketlerini ASLA bu fonksiyondan geçirmiyoruz.
    """
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ç", "c").replace("ö", "o").replace("ü", "u")
    s = re.sub(r"\s+", " ", s)
    return s


# -----------------------------
# Makam veri modeli (örnek set)
# -----------------------------
@dataclass
class MakamDef:
    name: str
    karar: str
    kutb: str     # Merkez
    agaz: str     # Başlangıç
    requires_nim: bool


# Not: Bu liste, senin 17'lik setinin tamamı olmayabilir; ama mantık doğru çalışır.
# Senin verdiğin kritik düzeltme:
# Uşşak: Karar=Dügâh, Kutb=Dügâh, Âgâz=Dügâh
MAKAMS: List[MakamDef] = [
    MakamDef("Uşşak", "Dügâh", "Dügâh", "Dügâh", False),
    MakamDef("Rast", "Rast", "Rast", "Rast", False),
    MakamDef("Hüseynî", "Dügâh", "Hüseynî", "Hüseynî", False),
    MakamDef("Nihâvend", "Rast", "Rast", "Rast", False),
    MakamDef("Kürdî", "Dügâh", "Dügâh", "Dügâh", False),
    MakamDef("Buselik", "Dügâh", "Dügâh", "Dügâh", False),
    MakamDef("Segâh", "Segâh", "Segâh", "Segâh", False),
    MakamDef("Mahûr", "Rast", "Rast", "Rast", False),

    # Nim gerektiren örnekler (filtre için):
    MakamDef("Hicâz", "Dügâh", "Nevâ", "Nevâ", True),
    MakamDef("Nikriz", "Rast", "Nevâ", "Nevâ", True),
    MakamDef("Sabâ", "Dügâh", "Çargâh", "Dügâh", True),
    MakamDef("Hüzzâm", "Segâh", "Nevâ", "Segâh", True),
    MakamDef("Karciğar", "Dügâh", "Nevâ", "Dügâh", True),
    MakamDef("Bayâtî", "Dügâh", "Nevâ", "Dügâh", True),
    MakamDef("Şehnâz", "Dügâh", "Nevâ", "Tiz Nevâ", True),
    MakamDef("Hümâyûn", "Dügâh", "Nevâ", "Dügâh", True),
]


# -----------------------------
# Nazari seyir tutarlılık filtresi (KRİTİK)
# -----------------------------
def nazari_compatible(m: MakamDef, features: Dict[str, str]) -> bool:
    """
    Kullanıcı bir alanı doldurduysa, o alanla ÇELİŞEN makam elenir.
    """
    if features.get("karar") and norm(features["karar"]) != norm(m.karar):
        return False
    if features.get("kutb") and norm(features["kutb"]) != norm(m.kutb):
        return False
    if features.get("agaz") and norm(features["agaz"]) != norm(m.agaz):
        return False
    return True


def score_makam(m: MakamDef, features: Dict[str, str]) -> float:
    """
    Skor: tutarlılık filtresinden geçmiş adayları sıralamak için hafif ağırlık.
    """
    score = 0.0
    if features.get("karar") and norm(features["karar"]) == norm(m.karar):
        score += 3.0
    if features.get("kutb") and norm(features["kutb"]) == norm(m.kutb):
        score += 2.0
    if features.get("agaz") and norm(features["agaz"]) == norm(m.agaz):
        score += 2.0
    return score


def rank_makams(makams: List[MakamDef], features: Dict[str, str], topk: int) -> List[Tuple[MakamDef, float]]:
    scored = [(m, score_makam(m, features)) for m in makams]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:topk]


def filter_makams_by_nim_name_evidence(makams: List[MakamDef], has_nim_name_evidence: bool) -> List[MakamDef]:
    if has_nim_name_evidence:
        return makams
    return [m for m in makams if not m.requires_nim]


# -----------------------------
# Mikrotonal teşhis (MusicXML) — filtreyi etkilemez
# -----------------------------
DIGITS_RE = re.compile(r"\b([1-9]|1[0-9])\b")


def extract_koma_number_from_text(text: str) -> Optional[int]:
    if not text:
        return None
    m = DIGITS_RE.search(text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def collect_note_attached_text(n: Any) -> str:
    texts: List[str] = []
    # lyrics
    try:
        for lyr in getattr(n, "lyrics", []) or []:
            t = getattr(lyr, "text", None)
            if t:
                texts.append(str(t))
    except Exception:
        pass
    # expressions / misc
    try:
        for ex in getattr(n, "expressions", []) or []:
            if hasattr(ex, "content"):
                texts.append(str(ex.content))
            else:
                texts.append(str(ex))
    except Exception:
        pass
    try:
        ed = getattr(n, "editorial", None)
        if ed and hasattr(ed, "misc") and isinstance(ed.misc, dict):
            for k, v in ed.misc.items():
                texts.append(f"{k}:{v}")
    except Exception:
        pass
    return " | ".join(texts)


def note_accidental_flags(n: Any) -> Tuple[bool, bool, bool, str]:
    acc_name = ""
    is_sharp = is_flat = is_natural = False
    try:
        acc = n.pitch.accidental
        if acc:
            acc_name = str(acc.name or acc)
            an = norm(acc.name or "")
            if "sharp" in an:
                is_sharp = True
            if "flat" in an:
                is_flat = True
            if "natural" in an:
                is_natural = True
    except Exception:
        pass
    return is_sharp, is_flat, is_natural, acc_name


def classify_interval_from_accidental(
    acc_name: str,
    is_sharp: bool,
    is_flat: bool,
    is_natural: bool,
    koma_number: Optional[int],
) -> str:
    # 1) Üst sayı override (Halk müziği)
    if koma_number is not None:
        if is_flat and koma_number in (1, 2, 3):
            return "koma_irha"
        if is_flat and koma_number == 4:
            return "bakiyye"
        if is_sharp and koma_number == 5:
            return "kucuk_mucenneb"
        return "unknown_micro"

    # 2) Metinden pest/dik yakala (sayı yoksa)
    a = norm(acc_name or "")
    if "pest" in a and ("sharp" in a or "diyez" in a or "diez" in a):
        return "bakiyye"
    if "dik" in a and ("sharp" in a or "diyez" in a or "diez" in a):
        return "buyuk_mucenneb"
    if "dik" in a and ("flat" in a or "bemol" in a):
        return "bakiyye"
    if "pest" in a and ("flat" in a or "bemol" in a):
        return "buyuk_mucenneb"
    if "pest" in a and ("natural" in a or "bekar" in a or "nat" in a):
        return "buyuk_mucenneb"
    if "dik" in a and ("natural" in a or "bekar" in a or "nat" in a):
        return "buyuk_mucenneb"

    # 3) Normal işaretler
    if is_sharp:
        # sayı yoksa diyez = Bakıyye (senin son kuralın)
        return "bakiyye"
    if is_flat:
        # sayı yoksa bemol = Küçük Mücenneb
        return "kucuk_mucenneb"
    if is_natural:
        return "natural"
    return "natural"


def detect_micro_intervals_in_score(score) -> Dict[str, Any]:
    counts: Dict[str, int] = {
        "natural": 0,
        "bakiyye": 0,
        "kucuk_mucenneb": 0,
        "buyuk_mucenneb": 0,
        "koma_irha": 0,
        "unknown_micro": 0,
    }
    samples: List[str] = []

    def handle_note(n: Any):
        is_sharp, is_flat, is_natural, acc_name = note_accidental_flags(n)
        attached_text = collect_note_attached_text(n)
        koma_n = extract_koma_number_from_text(attached_text)
        interval_class = classify_interval_from_accidental(
            acc_name=acc_name,
            is_sharp=is_sharp,
            is_flat=is_flat,
            is_natural=is_natural,
            koma_number=koma_n,
        )
        counts[interval_class] = counts.get(interval_class, 0) + 1
        if len(samples) < 12 and interval_class != "natural":
            try:
                pn = n.pitch.nameWithOctave
            except Exception:
                pn = "?"
            samples.append(
                f"- {pn} | accidental={acc_name or '—'} | text='{attached_text or '—'}' | koma={koma_n or '—'} => **{interval_class}**"
            )

    if score is None:
        return {"counts": counts, "has_micro": False, "samples": samples}

    for el in score.recurse():
        if isinstance(el, m21note.Note):
            handle_note(el)
        elif isinstance(el, m21chord.Chord):
            for nn in el.notes:
                handle_note(nn)

    has_micro = (counts["bakiyye"] + counts["kucuk_mucenneb"] + counts["buyuk_mucenneb"] + counts["koma_irha"] + counts["unknown_micro"]) > 0
    return {"counts": counts, "has_micro": has_micro, "samples": samples}


# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title="Makam Tahmini (Nazari Seyir + Nim Delili)", layout="wide")
st.title("Makam Olasılığı — Nazari Seyir (Âgâz, Kutb, Karar) + Nim Delili")

with st.sidebar:
    st.subheader("Dosya Yükleme")
    uploaded = st.file_uploader("MusicXML önerilir (xml/mxl). PDF sadece manuel nim için.", type=["xml", "musicxml", "mxl", "pdf"])
    st.caption("MusicXML: mikro işaretler sağda teşhis olarak görünür. Filtreyi nim-perde adı delili belirler.")

    st.markdown("---")
    st.subheader("Nazari Seyir")
    karar = st.text_input("Karar")
    kutb = st.text_input("Kutb (Merkez)")
    agaz = st.text_input("Âgâz (Başlangıç)")

    st.markdown("---")
    st.subheader("Nim perde adı delili (isim olarak)")

    # Unicode: Şurū = "Şurū" (u + combining macron) daha güvenli render
    SURU_LONG_U = "Şuru\u0304"   # Şurū
    # Zengûle: u şapkalı
    ZENG_CIRC = "Zengûle"

    NIM_NAME_OPTIONS: Dict[str, Tuple[str, List[str]]] = {
        "nim_hisar": ("Bayati / Nim Hisar", ["bayati", "nim hisar"]),
        "hisar": ("Dik Bayati / Hisar", ["dik bayati", "hisar"]),
        "dik_hisar": ("Pest Hüseyni / Dik Hisar", ["pest huseyni", "pest hüseyni", "dik hisar"]),

        "nim_hicaz": ("Saba / Nim Hicaz", ["saba", "nim hicaz"]),
        "hicaz": ("Dik Saba / Hicaz", ["dik saba", "hicaz"]),
        "dik_hicaz": ("Pest Neva / Dik Hicaz", ["pest neva", "dik hicaz"]),

        # Senin telaffuz kuralına göre: Şurū (u uzun), Zengûle (u şapkalı)
        "nim_zengule": (f"{SURU_LONG_U} / Nim {ZENG_CIRC}", ["şuri", "şurî", "şurī", "şurū", "nim zengule", "nim zengûle", "nim zengūle"]),
        "zengule": ("Dik Şuri / Zengule", ["dik şuri", "dik suri", "zengule", "zengüle"]),

        "dik_zengule": ("Pest Dügâh / Dik Zengûle", ["pest dugah", "pest dügâh", "dik zengule", "dik zengûle"]),

        "nim_sehnaz": ("Tiz Şuri / Nim Şehnaz", ["tiz şuri", "tiz suri", "nim sehnaz", "nim şehnaz"]),
        "sehnaz": ("Tiz Dik Şuri / Şehnaz", ["tiz dik şuri", "tiz dik suri", "sehnaz", "şehnaz"]),
    }

    labels = [v[0] for v in NIM_NAME_OPTIONS.values()]
    selected_labels = st.multiselect("Metinde/analizde adı geçenler (yoksa boş bırak)", labels)

    label_to_key = {v[0]: k for k, v in NIM_NAME_OPTIONS.items()}
    selected_keys = {label_to_key[lbl] for lbl in selected_labels if lbl in label_to_key}
    has_nim_name_evidence = len(selected_keys) > 0

    st.caption("Boş bırakırsan Hicâz gibi nim gerektiren makamlar filtrelenir.")

    st.markdown("---")
    st.subheader("PDF için manuel nim (isteğe bağlı)")
    manual_nim = st.checkbox("PDF yükledim ve nim perde adı delili var", value=False)
    topk = st.slider("Kaç sonuç gösterilsin?", 3, 17, 9)

features = {"karar": karar, "kutb": kutb, "agaz": agaz}

# Dosya okuma
file_kind = None
score_obj = None
micro = {"counts": {}, "has_micro": False, "samples": []}
file_error = None

if uploaded is not None:
    name = uploaded.name.lower()
    data = uploaded.read()

    if name.endswith((".xml", ".musicxml", ".mxl")):
        file_kind = "musicxml"
        if not M21_OK:
            file_error = "music21 yüklü değil. `pip install music21`"
        else:
            try:
                score_obj = converter.parse(io.BytesIO(data))
                micro = detect_micro_intervals_in_score(score_obj)
            except Exception as e:
                file_error = f"MusicXML parse edilemedi: {e}"
    elif name.endswith(".pdf"):
        file_kind = "pdf"

# Nim filtresi için esas: İSİM DELİLİ (ve PDF manuel)
has_nim_for_filter = bool(has_nim_name_evidence or (file_kind == "pdf" and manual_nim))

# 1) Nim filtresi
nim_filtered = filter_makams_by_nim_name_evidence(MAKAMS, has_nim_for_filter)

# 2) Nazari tutarlılık filtresi (KRİTİK)
nazari_filtered = [m for m in nim_filtered if nazari_compatible(m, features)]

# 3) Sıralama
ranked = rank_makams(nazari_filtered, features, topk)

# -----------------------------
# Output
# -----------------------------
left, right = st.columns([1.2, 1])

with left:
    st.subheader("Sonuçlar")

    if uploaded is not None:
        st.write("**Dosya:**", uploaded.name)
        if file_error:
            st.error(file_error)
        else:
            st.write("**Dosya türü:**", file_kind)

    st.write("**Nim delili (filtre):**", "✅ Var" if has_nim_for_filter else "❌ Yok")
    st.write("**Aday havuzu (nim filtresi sonrası):**", f"{len(nim_filtered)} / {len(MAKAMS)}")
    st.write("**Aday havuzu (nazari tutarlılık sonrası):**", f"{len(nazari_filtered)} / {len(nim_filtered)}")

    st.markdown("---")

    if not any(v.strip() for v in features.values()) and uploaded is None:
        st.info("Soldan Âgâz/Kutb/Karar gir veya (isteğe bağlı) MusicXML yükle.")
    else:
        if not ranked:
            st.warning("Bu Âgâz/Kutb/Karar kombinasyonuyla tutarlı makam bulunamadı (veya nim filtresi hepsini eledi).")
        for i, (m, sc) in enumerate(ranked, start=1):
            st.markdown(f"### {i}) {m.name}")
            st.write(f"Skor: **{sc:.2f}**")
            st.write(f"Karar: **{m.karar}**  |  Kutb: **{m.kutb}**  |  Âgâz: **{m.agaz}**")
            st.write(f"Nim gerektirir mi?: {'Evet' if m.requires_nim else 'Hayır'}")
            st.markdown("---")

with right:
    st.subheader("Mikrotonal Teşhis (MusicXML) — filtreyi etkilemez")
    if file_kind != "musicxml":
        st.info("Teşhis için MusicXML yükle. PDF'de otomatik mikro okuma yok.")
    elif file_error:
        st.warning("Dosya okunamadı; teşhis gösterilemiyor.")
    else:
        st.write("**Mikro (işaret/sayı teşhisi):**", "✅ Var" if micro.get("has_micro") else "❌ Yok")
        st.write("**Sayım (interval sınıfı):**")
        st.json(micro.get("counts", {}))

        st.markdown("**Örnek yakalamalar (ilk 12 mikro olay):**")
        if micro.get("samples"):
            st.markdown("\n".join(micro["samples"]))
        else:
            st.write("Mikro olay yakalanmadı (ya gerçekten yok, ya da export metni notaya bağlamamış olabilir).")

        st.markdown("---")
        st.subheader("Teşhis Kuralları (özet)")
        st.markdown(
            """
- **♯ üstünde sayı yoksa → Bakıyye**
- **♯⁵ → Küçük Mücenneb**
- **♭ üstünde sayı yoksa → Küçük Mücenneb**
- **♭⁴ → Bakıyye**
- **♭¹/²/³ → Koma/İrha**
- `pest/dik` metni varsa (sayı yoksa) özel sınıflar uygulanır.
"""
        )
