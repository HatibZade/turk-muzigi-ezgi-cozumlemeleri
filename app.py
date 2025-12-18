
# app.py
# Streamlit: Makam olasılığı + MusicXML mikrotonal işaret okuma (Halk müziği "koma sayıları" dahil)
# Python 3.10+
#
# NİM FİLTRESİ (kritik):
# - "Nim perde ismi vermediysem Hicaz gibi nimli makamlar olasılıklara girmesin" kuralı gereği,
#   nim filtresi NOTADAN tespit edilen mikro işaretlere göre değil, "isim delili" (kullanıcının seçtiği nim perde adları) ile çalışır.
# - Notadan mikro tespiti sağ tarafta sadece "teşhis" amaçlı gösterilir.
#
# Halk müziği sayı kuralları (override):
# - ♯ üzerinde sayı yoksa  => Bakıyye
# - ♯ üzerinde 5 varsa     => Küçük Mücenneb
# - ♭ üzerinde sayı yoksa  => Küçük Mücenneb
# - ♭ üzerinde 4 varsa     => Bakıyye
# - ♭ üzerinde 1/2/3 varsa => Koma/İrha
#
# Oklu/özel işaret kuralları (sayı yoksa):
# - pest diyez = bakıyye
# - diyez      = küçük mücenneb  (bu sadece "oklu tabloda" normal diyez için; sayı kuralları ve AEU/halk yazımı ağır basar)
# - dik diyez  = büyük mücenneb
# - dik bemol  = bakıyye
# - bemol      = küçük mücenneb
# - pest bemol = büyük mücenneb
# - dik diyez  = pest bekar
# - pest bemol = dik bekar
#
# Gereksinimler:
#   pip install streamlit music21

import io
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any

import streamlit as st

try:
    from music21 import converter
    from music21 import note as m21note
    from music21 import chord as m21chord
    M21_OK = True
except Exception:
    M21_OK = False


# -----------------------------
# Makam veri modeli (örnek)
# -----------------------------
@dataclass
class MakamDef:
    name: str
    karar: str
    kutb: str   # Merkez
    agaz: str   # Başlangıç (Âgâz)
    asil_alt: str
    asil_ust: str
    requires_nim: bool

MAKAMS: List[MakamDef] = [
    MakamDef("Rast", "Rast", "Rast", "Neva", "Yegâh", "Gerdâniye", False),
    MakamDef("Uşşak", "Dügâh", "Dügâh", "Neva", "Yegâh", "Gerdâniye", False),
    MakamDef("Hüseynî", "Dügâh", "Hüseynî", "Hüseynî", "Yegâh", "Tiz Hüseynî", False),
    MakamDef("Nihâvend", "Rast", "Rast", "Neva", "Yegâh", "Tiz Rast", False),
    MakamDef("Hicaz", "Dügâh", "Dügâh", "Neva", "Yegâh", "Gerdâniye", True),
    MakamDef("Kürdî", "Dügâh", "Dügâh", "Neva", "Yegâh", "Gerdâniye", False),
    MakamDef("Nikriz", "Rast", "Rast", "Neva", "Yegâh", "Gerdâniye", True),
    MakamDef("Sabâ", "Dügâh", "Dügâh", "Çargâh", "Yegâh", "Neva", True),
    MakamDef("Segâh", "Segâh", "Segâh", "Neva", "Yegâh", "Gerdâniye", False),
    MakamDef("Hüzzâm", "Segâh", "Segâh", "Neva", "Yegâh", "Gerdâniye", True),
    MakamDef("Bûselik", "Dügâh", "Dügâh", "Neva", "Yegâh", "Gerdâniye", False),
    MakamDef("Karcığar", "Dügâh", "Dügâh", "Neva", "Yegâh", "Gerdâniye", True),
    MakamDef("Bayâtî", "Dügâh", "Dügâh", "Neva", "Yegâh", "Gerdâniye", True),
    MakamDef("Şehnâz", "Dügâh", "Dügâh", "Neva", "Yegâh", "Tiz Neva", True),
    MakamDef("Mahûr", "Rast", "Rast", "Gerdâniye", "Yegâh", "Tiz Rast", False),
    MakamDef("Acemâşîrân", "Acemâşîrân", "Acemâşîrân", "Neva", "Rast", "Tiz Neva", False),
    MakamDef("Hümâyûn", "Dügâh", "Dügâh", "Neva", "Yegâh", "Gerdâniye", True),
]


# -----------------------------
# Normalizasyon (eşleme için)
# - Üst çizgi/şapka/diakritik: karşılaştırmada yok sayılır
# - Gösterimde ASLA normalize etmiyoruz
# -----------------------------
def norm(s: str) -> str:
    s = (s or "").strip().lower()

    # Birleşik diakritikleri çöz, sonra combining işaretleri kaldır
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))

    # Türkçe karakterleri sadeleştir
    s = (
        s.replace("ı", "i")
         .replace("ş", "s")
         .replace("ğ", "g")
         .replace("ç", "c")
         .replace("ö", "o")
         .replace("ü", "u")
    )
    s = re.sub(r"\s+", " ", s)
    return s


# -----------------------------
# Basit skor (UI özellikleri)
# -----------------------------
def score_makam(m: MakamDef, features: Dict[str, str]) -> float:
    score = 0.0
    if norm(features.get("karar", "")) == norm(m.karar):
        score += 3.0
    if norm(features.get("agaz", "")) == norm(m.agaz):
        score += 2.5
    if norm(features.get("kutb", "")) == norm(m.kutb):
        score += 2.0
    if norm(features.get("alt", "")) == norm(m.asil_alt):
        score += 1.5
    if norm(features.get("ust", "")) == norm(m.asil_ust):
        score += 1.5
    return score


def rank_makams(makams: List[MakamDef], features: Dict[str, str], topk: int) -> List[Tuple[MakamDef, float]]:
    scored = [(m, score_makam(m, features)) for m in makams]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:topk]


def filter_makams_by_nim(makams: List[MakamDef], allow_nim_makams: bool) -> List[MakamDef]:
    if allow_nim_makams:
        return makams
    return [m for m in makams if not m.requires_nim]


# -----------------------------
# Mikrotonal okuma: Halk müziği koma sayıları + oklu işaretler
# (Teşhis amaçlı)
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

    # Lyrics
    try:
        for lyr in getattr(n, "lyrics", []) or []:
            if getattr(lyr, "text", None):
                texts.append(str(lyr.text))
    except Exception:
        pass

    # Expressions
    try:
        for ex in getattr(n, "expressions", []) or []:
            if hasattr(ex, "content"):
                texts.append(str(ex.content))
            else:
                texts.append(str(ex))
    except Exception:
        pass

    # Editorial / misc
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
    """
    Çıktı sınıfları:
      - natural
      - bakiyye
      - kucuk_mucenneb
      - buyuk_mucenneb
      - koma_irha
      - unknown_micro
    """
    # 1) Halk müziği sayı override
    if koma_number is not None:
        if is_flat and koma_number in (1, 2, 3):
            return "koma_irha"
        if is_flat and koma_number == 4:
            return "bakiyye"
        if is_sharp and koma_number == 5:
            return "kucuk_mucenneb"
        # sayı var ama kural dışı ise yine mikro kabul et
        if is_sharp or is_flat:
            return "unknown_micro"

    # 2) Oklu/özel ad yakalama (export'a bağlı)
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
        return "buyuk_mucenneb"  # pest bekar = dik diyez
    if "dik" in a and ("natural" in a or "bekar" in a or "nat" in a):
        return "buyuk_mucenneb"  # dik bekar = pest bemol

    # 3) Sayı yoksa: senin nihai halk müziği kuralın
    if is_sharp:
        return "bakiyye"          # ♯ üstünde sayı yoksa bakiyye
    if is_flat:
        return "kucuk_mucenneb"   # ♭ üstünde sayı yoksa küçük mücenneb
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
                pitch_name = n.pitch.nameWithOctave
            except Exception:
                pitch_name = "?"
            samples.append(
                f"- {pitch_name} | accidental={acc_name or '—'} | text='{attached_text or '—'}' | koma={koma_n or '—'} => **{interval_class}**"
            )

    if score is None:
        return {"counts": counts, "has_micro": False, "samples": samples}

    for el in score.recurse():
        if isinstance(el, m21note.Note):
            handle_note(el)
        elif isinstance(el, m21chord.Chord):
            for nn in el.notes:
                handle_note(nn)

    has_micro = (
        counts["bakiyye"]
        + counts["kucuk_mucenneb"]
        + counts["buyuk_mucenneb"]
        + counts["koma_irha"]
        + counts["unknown_micro"]
    ) > 0

    return {"counts": counts, "has_micro": has_micro, "samples": samples}


# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title="Makam Tahmini (AEU/Halk Notasyonu + Nim İsim Delili)", layout="wide")
st.title("Makam Olasılığı — Nim İsim Delili + MusicXML Mikro Teşhis")

with st.sidebar:
    st.subheader("Dosya Yükleme")
    uploaded = st.file_uploader("MusicXML önerilir (xml/mxl). PDF teşhis için OCR yok.", type=["xml", "musicxml", "mxl", "pdf"])
    st.caption("Notadan mikro teşhis sağda gösterilir. Nim filtresi ise 'isim delili' ile çalışır.")

    st.markdown("---")
    st.subheader("Ezgi Özellikleri")
    karar = st.text_input("Karar")
    agaz = st.text_input("Âgâz (başlangıç)")
    kutb = st.text_input("Kutb (Merkez)")
    alt = st.text_input("Asıl alan alt sınır")
    ust = st.text_input("Asıl alan üst sınır")

    st.markdown("---")
    st.subheader("Nim perde adı delili (isim olarak)")
    # Şurî: u üst çizgi (uzatma) => Şurū, Nim Zengule: u şapkalı => Zengûle
    NIM_NAME_OPTIONS: Dict[str, Tuple[str, List[str]]] = {
        "nim_hisar": ("Bayâtî / Nim Hisâr", ["bayati", "bayati", "bayâtî", "nim hisar", "nim hisâr"]),
        "nim_hicaz": ("Sabâ / Nim Hicaz", ["saba", "sabâ", "nim hicaz"]),
        "nim_zengule": ("Şurū / Nim Zengûle", ["şuri", "şurî", "şurū", "suri", "nim zengule", "nim zengûle", "nim zengūle", "nim zengūle"]),
        "nim_sehnaz": ("Tiz Şurī / Nim Şehnâz", ["tiz şuri", "tiz şurî", "tiz şurī", "tiz suri", "nim şehnaz", "nim sehnaz", "nim şehnâz"]),

        # Çift ad gösterimleri (diyez/bemol yazımı)
        "dik_zengule": ("Pest Dügâh / Dik Zengûle", ["pest dügâh", "pest dugah", "dik zengule", "dik zengûle", "dik zengūle"]),
        "dik_hicaz": ("Pest Neva / Dik Hicaz", ["pest neva", "dik hicaz"]),
        "hisar": ("Dik Bayâtî / Hisâr", ["dik bayati", "dik bayâtî", "hisar", "hisâr"]),
        "dik_hisar": ("Pest Hüseynî / Dik Hisâr", ["pest hüseyni", "pest huseyni", "dik hisar", "dik hisâr"]),
        "zengule": ("Dik Şurī / Zengûle", ["dik şuri", "dik şurî", "dik şurī", "dik suri", "zengule", "zengûle", "zengūle"]),
        "hicaz": ("Dik Sabâ / Hicaz", ["dik saba", "dik sabâ", "hicaz"]),
        "sehnaz": ("Tiz Dik Şurī / Şehnâz", ["tiz dik şuri", "tiz dik şurî", "tiz dik şurī", "tiz dik suri", "şehnaz", "sehnaz", "şehnâz"]),
    }

    labels = [v[0] for v in NIM_NAME_OPTIONS.values()]
    selected_labels = st.multiselect(
        "Metinde/analizde adı geçen nim perdeler (yoksa boş bırak)",
        labels
    )

    label_to_key = {v[0]: k for k, v in NIM_NAME_OPTIONS.items()}
    selected_keys = {label_to_key[lbl] for lbl in selected_labels if lbl in label_to_key}
    has_nim_name_evidence = len(selected_keys) > 0
    st.caption("Boş bırakırsan Hicaz/Nikriz/Sabâ gibi nimli makamlar filtrelenir (notada mikro olsa bile).")

    st.markdown("---")
    topk = st.slider("Kaç sonuç gösterilsin?", 3, 17, 9)

features = {"karar": karar, "kutb": kutb, "agaz": agaz, "alt": alt, "ust": ust}

file_kind = None
score = None
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
                score = converter.parse(io.BytesIO(data))
                micro = detect_micro_intervals_in_score(score)
            except Exception as e:
                file_error = f"MusicXML parse edilemedi: {e}"
    elif name.endswith(".pdf"):
        file_kind = "pdf"

# Nim filtresinde ESAS: isim delili
allow_nim_makams = has_nim_name_evidence

# Teşhis: notadan mikro var mı?
has_micro_from_score = bool(micro.get("has_micro", False)) if file_kind == "musicxml" else False

candidates = filter_makams_by_nim(MAKAMS, allow_nim_makams)
ranked = rank_makams(candidates, features, topk)

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

    st.write("**Nim (isim delili, filtre):**", "✅ Var" if allow_nim_makams else "❌ Yok")
    if file_kind == "musicxml" and not file_error:
        st.write("**Mikro (işaretlerden teşhis):**", "✅ Var" if has_micro_from_score else "❌ Yok")

    st.write("**Nim filtresi sonrası aday havuz:**", f"{len(candidates)} / {len(MAKAMS)}")
    st.markdown("---")

    if not any(v.strip() for v in features.values()) and uploaded is None:
        st.info("Soldan MusicXML yükle veya ezgi özelliklerini gir.")
    else:
        for i, (m, sc) in enumerate(ranked, start=1):
            st.markdown(f"### {i}) {m.name}")
            st.write(f"Skor: **{sc:.2f}**")
            st.write(f"Karar: {m.karar} — Âgâz: {m.agaz} — Kutb: {m.kutb}")
            st.write(f"Asıl alan: {m.asil_alt} → {m.asil_ust}")
            st.write(f"Nim gerektirir mi?: {'Evet' if m.requires_nim else 'Hayır'}")
            st.markdown("---")

with right:
    st.subheader("Mikrotonal Okuma Teşhisi (MusicXML)")
    if file_kind != "musicxml":
        st.info("Teşhis için MusicXML yükle (PDF'de OCR yoksa sayı okunamaz).")
    elif file_error:
        st.warning("Dosya okunamadı; teşhis gösterilemiyor.")
    else:
        counts = micro.get("counts", {})
        st.write("**Sayım (interval sınıfı):**")
        st.json(counts)

        st.markdown("**Örnek yakalamalar (ilk 12 mikro olay):**")
        if micro.get("samples"):
            st.markdown("\n".join(micro["samples"]))
        else:
            st.write("Mikro olay yakalanmadı (ya gerçekten yok, ya da export metni notaya bağlamamış olabilir).")

        st.markdown("---")
        st.subheader("Okuma Kuralları (özet, teşhis için)")
        st.markdown(
            """
**Halk müziği sayı override**
- ♯ üstünde sayı yoksa → **Bakıyye**
- ♯⁵ → **Küçük Mücenneb**
- ♭ üstünde sayı yoksa → **Küçük Mücenneb**
- ♭⁴ → **Bakıyye**
- ♭¹/²/³ → **Koma/İrha**

**Oklu/özel işaretler (sayı yoksa)**
- pest diyez → Bakıyye
- dik diyez → Büyük Mücenneb
- dik bemol → Bakıyye
- pest bemol → Büyük Mücenneb
- pest bekar ↔ dik diyez
- dik bekar ↔ pest bemol

> Not: Makam filtresi bu teşhise göre değil, soldaki **nim isim delili** seçimine göre çalışır.
"""
        )
