# app.py
# Streamlit: Makam olasılığı + MusicXML mikrotonal işaret okuma (Halk müziği koma sayıları dahil)
# Python 3.10+
#
# Kurallar (nihai):
#  - ♯ üzerinde sayı yoksa => Bakıyye
#  - ♯ üzerinde 5 varsa   => Küçük Mücenneb
#  - ♭ üzerinde sayı yoksa => Küçük Mücenneb
#  - ♭ üzerinde 4 varsa   => Bakıyye
#  - ♭ üzerinde 1/2/3 varsa => Koma/İrha (mikro ama sınıf dışı ince ayar)
#  - Oklu/özel işaretler (sayı yoksa):
#      pest diyez = Bakıyye
#      dik diyez  = Büyük Mücenneb
#      dik bemol  = Bakıyye
#      pest bemol = Büyük Mücenneb
#      dik diyez  = pest bekar
#      pest bemol = dik bekar
#
# Nim tespiti:
#  - natural (işaretsiz) dışındaki her şey nim delilidir.
#
# Gereksinimler:
#   pip install streamlit music21

import io
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
import streamlit as st

try:
    from music21 import converter
    from music21 import note as m21note
    from music21 import chord as m21chord
    from music21 import expressions as m21expr
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
    guclu: str
    merkez: str
    asil_alt: str
    asil_ust: str
    # "nim gerektirir mi?" basit flag; isterse perdelerden de türetebilirsin
    requires_nim: bool


MAKAMS: List[MakamDef] = [
    MakamDef("Rast", "Rast", "Neva", "Rast", "Yegah", "Gerdaniye", False),
    MakamDef("Uşşak", "Dügah", "Neva", "Dügah", "Yegah", "Gerdaniye", False),
    MakamDef("Hüseyni", "Dügah", "Hüseyni", "Hüseyni", "Yegah", "Tiz Hüseyni", False),
    MakamDef("Nihavend", "Rast", "Neva", "Rast", "Yegah", "Tiz Rast", False),
    MakamDef("Hicaz", "Dügah", "Neva", "Dügah", "Yegah", "Gerdaniye", True),
    MakamDef("Kürdî", "Dügah", "Neva", "Dügah", "Yegah", "Gerdaniye", False),
    MakamDef("Nikriz", "Rast", "Neva", "Rast", "Yegah", "Gerdaniye", True),
    MakamDef("Saba", "Dügah", "Çargah", "Dügah", "Yegah", "Neva", True),
    MakamDef("Segah", "Segah", "Neva", "Segah", "Yegah", "Gerdaniye", False),
    MakamDef("Hüzzam", "Segah", "Neva", "Segah", "Yegah", "Gerdaniye", True),
    MakamDef("Buselik", "Dügah", "Neva", "Dügah", "Yegah", "Gerdaniye", False),
    MakamDef("Karciğar", "Dügah", "Neva", "Dügah", "Yegah", "Gerdaniye", True),
    MakamDef("Bayati", "Dügah", "Neva", "Dügah", "Yegah", "Gerdaniye", True),
    MakamDef("Şehnaz", "Dügah", "Neva", "Dügah", "Yegah", "Tiz Neva", True),
    MakamDef("Mahur", "Rast", "Gerdaniye", "Rast", "Yegah", "Tiz Rast", False),
    MakamDef("Acem Aşiran", "Acem Aşiran", "Neva", "Acem Aşiran", "Rast", "Tiz Neva", False),
    MakamDef("Hümayun", "Dügah", "Neva", "Dügah", "Yegah", "Gerdaniye", True),
]


# -----------------------------
# String normalizasyon
# -----------------------------
def norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ç", "c").replace("ö", "o").replace("ü", "u")
    s = re.sub(r"\s+", " ", s)
    return s


# -----------------------------
# Basit skor (UI özellikleri)
# -----------------------------
def score_makam(m: MakamDef, features: Dict[str, str]) -> float:
    score = 0.0
    if norm(features.get("karar", "")) == norm(m.karar):
        score += 3.0
    if norm(features.get("guclu", "")) == norm(m.guclu):
        score += 2.5
    if norm(features.get("merkez", "")) == norm(m.merkez):
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


def filter_makams_by_nim(makams: List[MakamDef], has_nim: bool) -> List[MakamDef]:
    if has_nim:
        return makams
    return [m for m in makams if not m.requires_nim]


# -----------------------------
# Mikrotonal okuma: Halk müziği koma sayıları + oklu işaretler
# -----------------------------
DIGITS_RE = re.compile(r"\b([1-9]|1[0-9])\b")

def extract_koma_number_from_text(text: str) -> Optional[int]:
    """
    Metinden ilk görülen sayıyı alır.
    Örn: "♭4" / "b4" / "koma 4" / "4" -> 4
    """
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
    """
    music21 Note üzerinde (varsa) sayı yakalamak için erişilebilecek metinleri toplar.
    Not: MusicXML export'a göre değişebilir; bu yüzden çoklu kaynaktan ararız.
    """
    texts: List[str] = []

    # Lyrics
    try:
        for lyr in getattr(n, "lyrics", []) or []:
            if getattr(lyr, "text", None):
                texts.append(str(lyr.text))
    except Exception:
        pass

    # Expressions (TextExpression vs.)
    try:
        for ex in getattr(n, "expressions", []) or []:
            # TextExpression olabilir
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


def classify_interval_from_accidental(
    acc_name: str,
    is_sharp: bool,
    is_flat: bool,
    is_natural: bool,
    koma_number: Optional[int],
) -> str:
    """
    Nihai sınıf döndürür:
      - natural
      - bakiyye
      - kucuk_mucenneb
      - buyuk_mucenneb
      - koma_irha (1/2/3)
      - unknown_micro (mikro ama sınıf belirsiz)
    Öncelik: koma_number override.
    """
    # 1) Koma/üst sayı override (Halk müziği kuralı)
    if koma_number is not None:
        # Bemol üstü 1/2/3: koma/irha
        if is_flat and koma_number in (1, 2, 3):
            return "koma_irha"
        # Bemol üstü 4: bakiyye bemol
        if is_flat and koma_number == 4:
            return "bakiyye"
        # Diyez üstü 5: küçük mücenneb
        if is_sharp and koma_number == 5:
            return "kucuk_mucenneb"
        # Diyez üstünde başka sayı varsa: mikro ama belirsiz
        if is_sharp:
            return "unknown_micro"
        # Bemolde başka sayı varsa: mikro ama belirsiz
        if is_flat:
            return "unknown_micro"

    # 2) Oklu/özel işaret yakalama (sayı yoksa)
    a = norm(acc_name or "")

    # Not: MusicXML/Font'a göre farklı isimler gelebilir. Burada olabildiğince kapsayıcı davranıyoruz.
    # Aşağıdakiler, özellikle "pest"/"dik" gibi metinler taşınırsa çalışır.
    if "pest" in a and ("sharp" in a or "diez" in a or "diyez" in a):
        return "bakiyye"  # pest diyez = bakiyye
    if "dik" in a and ("sharp" in a or "diez" in a or "diyez" in a):
        return "buyuk_mucenneb"  # dik diyez = büyük mücenneb

    if "dik" in a and ("flat" in a or "bemol" in a):
        return "bakiyye"  # dik bemol = bakiyye
    if "pest" in a and ("flat" in a or "bemol" in a):
        return "buyuk_mucenneb"  # pest bemol = büyük mücenneb

    # bekar (natural) varyantları (eşdeğerlik)
    if "pest" in a and ("natural" in a or "bekar" in a or "nat" in a):
        return "buyuk_mucenneb"  # pest bekar = dik diyez = büyük mücenneb
    if "dik" in a and ("natural" in a or "bekar" in a or "nat" in a):
        return "buyuk_mucenneb"  # dik bekar = pest bemol = büyük mücenneb

    # 3) Normal işaretler (nihai kural seti)
    if is_sharp:
        # diyez üzerinde sayı yoksa => bakiyye
        return "bakiyye"
    if is_flat:
        # bemol üzerinde sayı yoksa => küçük mücenneb
        return "kucuk_mucenneb"
    if is_natural:
        return "natural"

    return "natural"


def note_accidental_flags(n: Any) -> Tuple[bool, bool, bool, str]:
    """
    Note'un accidental'ını music21 üzerinden okur.
    Dönen: is_sharp, is_flat, is_natural, acc_name
    """
    acc_name = ""
    is_sharp = is_flat = is_natural = False
    try:
        acc = n.pitch.accidental
        if acc:
            acc_name = str(acc.name or acc)
            # music21'daki temel isimler genelde: 'sharp', 'flat', 'natural', 'double-sharp', etc.
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


def detect_micro_intervals_in_score(score) -> Dict[str, Any]:
    """
    Score içindeki notalardan:
      - interval_class sayımı
      - nim var mı?
      - örnek açıklama satırları
    üretir.
    """
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

        # örnek satır
        if len(samples) < 12 and (interval_class != "natural"):
            pitch_name = ""
            try:
                pitch_name = n.pitch.nameWithOctave
            except Exception:
                pitch_name = "?"
            samples.append(
                f"- {pitch_name} | accidental={acc_name or '—'} | text='{attached_text or '—'}' | koma={koma_n or '—'} => **{interval_class}**"
            )

    if score is None:
        return {"counts": counts, "has_nim": False, "samples": samples}

    for el in score.recurse():
        if isinstance(el, m21note.Note):
            handle_note(el)
        elif isinstance(el, m21chord.Chord):
            # chord içindeki pitch'leri note gibi ele almak yerine chord'un notalarını gez
            for nn in el.notes:
                handle_note(nn)

    has_nim = (
        counts["bakiyye"]
        + counts["kucuk_mucenneb"]
        + counts["buyuk_mucenneb"]
        + counts["koma_irha"]
        + counts["unknown_micro"]
    ) > 0

    return {"counts": counts, "has_nim": has_nim, "samples": samples}


# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title="Makam Tahmini (AEU + Halk Müziği Koma Sayıları)", layout="wide")
st.title("Makam Olasılığı — AEU/Halk Müziği İşaret Okuma + Nim Filtresi")

with st.sidebar:
    st.subheader("Dosya Yükleme")
    uploaded = st.file_uploader("MusicXML önerilir (pdf/xml/mxl)", type=["xml", "musicxml", "mxl", "pdf"])
    st.caption("Halk müziği 'koma sayıları' MusicXML içinde metin olarak gelirse yakalanır. PDF'de OCR yoksa sayı okuma yapılamaz.")

    st.subheader("Ezgi Özellikleri")
    karar = st.text_input("Karar")
    guclu = st.text_input("Güçlü")
    merkez = st.text_input("Merkez")
    alt = st.text_input("Asıl alan alt sınır")
    ust = st.text_input("Asıl alan üst sınır")

    st.markdown("---")
    st.subheader("PDF için manuel nim")
    manual_nim = st.checkbox("PDF yükledim ve ezgide mikro (nim) var", value=False)
    topk = st.slider("Kaç sonuç gösterilsin?", 3, 17, 9)

features = {"karar": karar, "guclu": guclu, "merkez": merkez, "alt": alt, "ust": ust}

file_kind = None
score = None
micro = {"counts": {}, "has_nim": False, "samples": []}
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

# Nim var mı?
if file_kind == "musicxml":
    has_nim = bool(micro.get("has_nim", False))
elif file_kind == "pdf":
    has_nim = bool(manual_nim)
else:
    # dosya yoksa sadece UI ile tahmin (nim bilgisi yok)
    has_nim = False

candidates = filter_makams_by_nim(MAKAMS, has_nim)
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
            st.write("**Nim (mikro) tespiti:**", "✅ Var" if has_nim else "❌ Yok")

    st.write("**Nim filtresi sonrası aday havuz:**", f"{len(candidates)} / {len(MAKAMS)}")
    st.markdown("---")

    if not any(v.strip() for v in features.values()) and uploaded is None:
        st.info("Soldan MusicXML yükle veya ezgi özelliklerini gir.")
    else:
        for i, (m, sc) in enumerate(ranked, start=1):
            st.markdown(f"### {i}) {m.name}")
            st.write(f"Skor: **{sc:.2f}**")
            st.write(f"Karar: {m.karar} — Güçlü: {m.guclu} — Merkez: {m.merkez}")
            st.write(f"Asıl alan: {m.asil_alt} → {m.asil_ust}")
            st.write(f"Nim gerektirir mi?: {'Evet' if m.requires_nim else 'Hayır'}")
            st.markdown("---")

with right:
    st.subheader("Mikrotonal Okuma Teşhisi (MusicXML)")
    if file_kind != "musicxml":
        st.info("Mikrotonal teşhis için MusicXML yükle (PDF'de OCR yoksa sayı okunamaz).")
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
        st.subheader("Okuma Kuralları (özet)")
        st.markdown(
            """
- **♯ üstünde sayı yoksa → Bakıyye**
- **♯⁵ → Küçük Mücenneb**
- **♭ üstünde sayı yoksa → Küçük Mücenneb**
- **♭⁴ → Bakıyye**
- **♭¹/²/³ → Koma/İrha**
- Oklu/özel işaretler (sayı yoksa):
  - pest diyez → Bakıyye
  - dik diyez → Büyük Mücenneb
  - dik bemol → Bakıyye
  - pest bemol → Büyük Mücenneb
  - pest bekar ↔ dik diyez
  - dik bekar ↔ pest bemol
"""
        )
