# app_latest.py
# Streamlit: Makam olasılığı + MusicXML mikrotonal teşhis (AEU/Halk müziği işaretleri)
# Bu sürümün kritik davranışları:
#  1) Nazari Seyir alanları: Âgâz (başlangıç), Kutb (Merkez), Karar
#  2) Nazari Seyir "sert filtre": girilen alanlar birebir uyuşmuyorsa makam elenir.
#     Eğer sert filtre sonucu 0 aday kalırsa, otomatik "yumuşak mod"a geçer:
#        - sadece Karar üzerinden eleme yapılır; Âgâz/Kutb skorla etkiler.
#  3) Nim filtresi: SADECE "nim perde adı delili" (isim olarak) üzerinden çalışır.
#     MusicXML'den mikro işaret tespiti sağda teşhis olarak gösterilir; filtreyi delmez.
#
# Gereksinimler:
#   pip install streamlit music21

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
# Yardımcı: karşılaştırma için normalize
# (NOT: UI etiketleri asla normalize edilmez)
# -----------------------------
def norm(s: str) -> str:
    s = (s or "").strip().lower()
    # Diakritikleri sök (şurî/şurī/şuri -> aynı anahtar)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
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
# Makam veri modeli
# -----------------------------
@dataclass
class MakamDef:
    name: str
    karar: str
    kutb: str   # merkez
    agaz: str
    asil_alt: str
    asil_ust: str
    requires_nim: bool


# NOT: Bu liste örnek/başlangıç setidir. Senin gerçek 17 makam tanımın varsa burayı onunla doldurmalısın.
# Buradaki en önemli şey: Uşşak tanımı "dügah, dügah, dügah" olmalıdır (senin dediğin gibi).
MAKAMS: List[MakamDef] = [
    MakamDef("Uşşak", "Dügâh", "Dügâh", "Dügâh", "Yegâh", "Gerdâniye", False),
    MakamDef("Nevâ", "Dügâh", "Nevâ", "Nevâ", "Yegâh", "Tiz Nevâ", False),
    MakamDef("Rast", "Rast", "Rast", "Rast", "Yegâh", "Gerdâniye", False),
    MakamDef("Hüseynî", "Dügâh", "Hüseynî", "Dügâh", "Yegâh", "Tiz Hüseynî", False),
    MakamDef("Nihâvend", "Rast", "Rast", "Rast", "Yegâh", "Tiz Rast", False),
    MakamDef("Hicaz", "Dügâh", "Nevâ", "Nevâ", "Yegâh", "Gerdâniye", True),
    MakamDef("Saba", "Dügâh", "Çargâh", "Dügâh", "Yegâh", "Nevâ", True),
    MakamDef("Nikriz", "Rast", "Nevâ", "Rast", "Yegâh", "Gerdâniye", True),
    MakamDef("Segâh", "Segâh", "Segâh", "Segâh", "Yegâh", "Gerdâniye", False),
    MakamDef("Hüzzam", "Segâh", "Nevâ", "Segâh", "Yegâh", "Gerdâniye", True),
    MakamDef("Bayâtî", "Dügâh", "Nevâ", "Nevâ", "Yegâh", "Gerdâniye", True),
    MakamDef("Şehnâz", "Dügâh", "Nevâ", "Tiz Nevâ", "Yegâh", "Tiz Nevâ", True),
]


# -----------------------------
# Nazari filtre + skor
# -----------------------------
def nazari_filter_strict(m: MakamDef, f: Dict[str, str]) -> bool:
    # girilen alanlar boş değilse birebir eşleşme zorunlu
    if f.get("karar") and norm(f["karar"]) != norm(m.karar):
        return False
    if f.get("merkez") and norm(f["merkez"]) != norm(m.kutb):
        return False
    if f.get("agaz") and norm(f["agaz"]) != norm(m.agaz):
        return False
    return True


def nazari_filter_soft(m: MakamDef, f: Dict[str, str]) -> bool:
    # yumuşak mod: sadece karar eleme kriteri
    if f.get("karar") and norm(f["karar"]) != norm(m.karar):
        return False
    return True


def score_makam(m: MakamDef, f: Dict[str, str]) -> float:
    # yumuşak modda da sıralama için kullanılır; sert modda zaten filtrelenmiş adaylar skorlanır.
    score = 0.0
    if f.get("karar") and norm(f["karar"]) == norm(m.karar):
        score += 4.0
    if f.get("merkez") and norm(f["merkez"]) == norm(m.kutb):
        score += 3.0
    if f.get("agaz") and norm(f["agaz"]) == norm(m.agaz):
        score += 2.5
    # alan sınırları (opsiyonel)
    if f.get("alt") and norm(f["alt"]) == norm(m.asil_alt):
        score += 1.0
    if f.get("ust") and norm(f["ust"]) == norm(m.asil_ust):
        score += 1.0
    return score


def rank_makams(makams: List[MakamDef], f: Dict[str, str], topk: int) -> List[Tuple[MakamDef, float]]:
    scored = [(m, score_makam(m, f)) for m in makams]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:topk]


def filter_makams_by_nim(makams: List[MakamDef], has_nim_name_evidence: bool) -> List[MakamDef]:
    if has_nim_name_evidence:
        return makams
    return [m for m in makams if not m.requires_nim]


# -----------------------------
# MusicXML mikrotonal teşhis (filtreyi etkilemez)
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
            if getattr(lyr, "text", None):
                texts.append(str(lyr.text))
    except Exception:
        pass
    # expressions
    try:
        for ex in getattr(n, "expressions", []) or []:
            if hasattr(ex, "content"):
                texts.append(str(ex.content))
            else:
                texts.append(str(ex))
    except Exception:
        pass
    # editorial misc
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
    Teşhis sınıfı:
      natural | bakiyye | kucuk_mucenneb | buyuk_mucenneb | koma_irha | unknown_micro
    Kural seti (senin son kararların):
      - Diyezde sayı yoksa: bakiyye
      - Diyezde 5 varsa: küçük mücenneb
      - Bemolde sayı yoksa: küçük mücenneb
      - Bemolde 4 varsa: bakiyye
      - Bemolde 1/2/3 varsa: koma/irha
      - Oklu işaretler (metinden yakalanırsa) sayı yoksa devreye girer
    """
    # 1) sayı override
    if koma_number is not None:
        if is_flat and koma_number in (1, 2, 3):
            return "koma_irha"
        if is_flat and koma_number == 4:
            return "bakiyye"
        if is_sharp and koma_number == 5:
            return "kucuk_mucenneb"
        # başka sayılar -> mikro ama sınıf belirsiz
        if is_sharp or is_flat:
            return "unknown_micro"

    # 2) oklu/özel isim yakalama (sayı yoksa)
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

    # 3) normal işaretler
    if is_sharp:
        return "bakiyye"
    if is_flat:
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
st.set_page_config(page_title="Nazari Seyir + Nim Filtresi", layout="wide")
st.title("Makam Olasılığı — Nazari Seyir (Âgâz / Kutb / Karar) + Nim İsim Delili")

with st.sidebar:
    st.subheader("Dosya Yükleme")
    uploaded = st.file_uploader("MusicXML (xml/mxl) önerilir", type=["xml", "musicxml", "mxl", "pdf"])
    st.caption("MusicXML mikro işaret teşhisi sağda gösterilir. Nim filtresi isim deliline göre çalışır.")

    st.markdown("---")
    st.subheader("Nazari Seyir")
    karar = st.text_input("Karar")
    merkez = st.text_input("Kutb (Merkez)")
    agaz = st.text_input("Âgâz (Başlangıç)")

    st.markdown("---")
    st.subheader("Asıl Alan (opsiyonel)")
    alt = st.text_input("Asıl alan alt sınır")
    ust = st.text_input("Asıl alan üst sınır")

    st.markdown("---")
    st.subheader("Nim perde adı delili (isim olarak)")
    # UI etiketleri telaffuz işaretleriyle doğru verilir.
    NIM_NAME_OPTIONS: Dict[str, Tuple[str, List[str]]] = {
        "nim_hisar": ("Bayâtî / Nim Hisar", ["bayati", "bayâtî", "nim hisar"]),
        "nim_hicaz": ("Saba / Nim Hicaz", ["saba", "nim hicaz"]),
        # Şurū: u üst çizgi (uzatma). Zengûle: u şapka (yumuşatma).
        "nim_zengule": ("Şurū / Nim Zengûle", ["şurū", "şurî", "şuri", "nim zengûle", "nim zengule", "nim zengūle"]),
        "nim_sehnaz": ("Tiz Şurū / Nim Şehnâz", ["tiz şurū", "tiz şuri", "nim şehnaz", "nim sehnaz"]),
        # Çift ad düzeltmesi:
        "dik_zengule": ("Pest Dügâh / Dik Zengûle", ["pest dügâh", "pest dugah", "dik zengule", "dik zengûle"]),
        "dik_hicaz": ("Pest Nevâ / Dik Hicaz", ["pest neva", "pest nevâ", "dik hicaz"]),
        "hisar": ("Dik Bayâtî / Hisar", ["dik bayati", "dik bayâtî", "hisar"]),
        "dik_hisar": ("Pest Hüseynî / Dik Hisar", ["pest huseyni", "pest hüseynî", "dik hisar"]),
        "zengule": ("Dik Şurū / Zengûle", ["dik şurū", "dik şuri", "zengule", "zengûle"]),
        "hicaz": ("Dik Saba / Hicaz", ["dik saba", "hicaz"]),
        "sehnaz": ("Tiz Dik Şurū / Şehnâz", ["tiz dik şurū", "tiz dik şuri", "şehnaz", "şehnâz", "sehnaz"]),
    }

    labels = [v[0] for v in NIM_NAME_OPTIONS.values()]
    selected_labels = st.multiselect("Metinde/analizde adı geçenler (yoksa boş bırak)", labels)
    label_to_key = {v[0]: k for k, v in NIM_NAME_OPTIONS.items()}
    selected_keys = {label_to_key[lbl] for lbl in selected_labels if lbl in label_to_key}
    has_nim_name_evidence = len(selected_keys) > 0
    st.caption("Boş bırakırsan Hicaz gibi nim gerektiren makamlar filtrelenir.")

    st.markdown("---")
    topk = st.slider("Kaç sonuç gösterilsin?", 3, 25, 9)


features = {"karar": karar, "merkez": merkez, "agaz": agaz, "alt": alt, "ust": ust}

# MusicXML teşhis
file_kind = None
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

# Nim filtresi yalnız isim deliline göre:
has_nim_for_filter = has_nim_name_evidence

# 1) Nim filtresi
candidates0 = filter_makams_by_nim(MAKAMS, has_nim_for_filter)

# 2) Nazari filtre: önce sert, 0 ise yumuşak
candidates = [m for m in candidates0 if nazari_filter_strict(m, features)]
used_soft = False
# Yumuşatma: sadece Karar girilmişse (Âgâz/Kutb boşsa) devreye girsin.
if len(candidates) == 0 and not (features.get("agaz") or features.get("merkez")):
    candidates = [m for m in candidates0 if nazari_filter_soft(m, features)]
    used_soft = True

ranked = rank_makams(candidates, features, topk)

# -----------------------------
# Output
# -----------------------------
left, right = st.columns([1.25, 1])

with left:
    st.subheader("Sonuçlar")
    if uploaded is not None:
        st.write("**Dosya:**", uploaded.name)
        st.write("**Dosya türü:**", file_kind)
        if file_error:
            st.error(file_error)

    st.write("**Nim filtresi (isim delili):**", "✅ Var" if has_nim_for_filter else "❌ Yok")
    if file_kind == "musicxml" and not file_error:
        st.write("**Mikro işaret teşhisi (MusicXML):**", "✅ Var" if micro.get("has_micro") else "❌ Yok")

    if used_soft:
        st.warning("Girdiğin Karar/Âgâz/Kutb üçlüsüne birebir uyan tanım listede bulunamadı. Sadece Karar ile yumuşatılmış arama gösteriliyor.")

    st.write("**Aday havuz:**", f"{len(candidates)} / {len(MAKAMS)}")
    st.markdown("---")

    if len(ranked) == 0:
        if features.get("agaz") or features.get("merkez"):
            st.error("Bu Karar/Âgâz/Kutb kombinasyonuna uyan makam tanımı listede yok. (Tanım setini 17 makamına göre güncelle.)")
        else:
            st.error("Uygun makam bulunamadı. (Tanım listeni ve yazımını kontrol et.)")
    else:
        for i, (m, sc) in enumerate(ranked, start=1):
            st.markdown(f"### {i}) {m.name}")
            st.write(f"Skor: **{sc:.2f}**")
            st.write(f"Karar: {m.karar} — Kutb: {m.kutb} — Âgâz: {m.agaz}")
            st.write(f"Asıl alan: {m.asil_alt} → {m.asil_ust}")
            st.write(f"Nim gerektirir mi?: {'Evet' if m.requires_nim else 'Hayır'}")
            st.markdown("---")

with right:
    st.subheader("Mikrotonal Teşhis (MusicXML)")
    if file_kind != "musicxml":
        st.info("Teşhis için MusicXML yükle (PDF’de sayı/işaret okumak burada yapılmıyor).")
    elif file_error:
        st.warning("Dosya okunamadı; teşhis gösterilemiyor.")
    else:
        st.write("**Sayım (interval sınıfı):**")
        st.json(micro.get("counts", {}))
        st.markdown("**Örnek yakalamalar (ilk 12 mikro olay):**")
        if micro.get("samples"):
            st.markdown("\n".join(micro["samples"]))
        else:
            st.write("Mikro olay yakalanmadı (ya yok, ya da export metni notaya bağlamamış olabilir).")

        st.markdown("---")
        st.subheader("Teşhis Kuralları (özet)")
        st.markdown(
            """
- **♯ üstünde sayı yoksa → Bakıyye**
- **♯⁵ → Küçük Mücenneb**
- **♭ üstünde sayı yoksa → Küçük Mücenneb**
- **♭⁴ → Bakıyye**
- **♭¹/²/³ → Koma/İrha**
- Oklu/özel işaret metinleri (sayı yoksa):
  - pest diyez → Bakıyye
  - dik diyez → Büyük Mücenneb
  - dik bemol → Bakıyye
  - pest bemol → Büyük Mücenneb
  - pest bekar ↔ dik diyez
  - dik bekar ↔ pest bemol

> Bu teşhis, **nim filtresini etkilemez**; nim filtresi yalnız “isim delili” ile çalışır.
"""
        )
